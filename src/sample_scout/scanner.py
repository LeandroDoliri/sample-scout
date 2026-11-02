"""Escaneo de carpetas y análisis en paralelo.

Prioridad de fuentes para cada dato:
  corrección manual (`user`) > metadata embebida (`meta`) > nombre/carpeta (`name`)
  > análisis de audio (`audio`)

Lo que corrigió el usuario vive en `user_fields` (ver db.py) y se vuelve a aplicar cada vez que
un archivo se indexa, así que ni re-escanear ni re-analizar lo pisan.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from sample_scout import db
from sample_scout.metadata import read_acid
from sample_scout.parser import DRUM_INSTRUMENTS, parse_path

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
COVER_WORDS = ("cover", "artwork", "folder", "front", "albumart")
Progress = Callable[[str], None]


def _norm(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


class CoverFinder:
    """Portada de cada carpeta de una raíz: la imagen más cercana subiendo desde la carpeta del
    sample hasta `root` (nunca más arriba). En cada nivel gana una imagen con nombre de portada
    (`cover…`, `artwork…`, `folder…`, `front…`, o el nombre de esa carpeta o del pack); si no
    hay, la más pesada. Lista cada carpeta una sola vez."""

    def __init__(self, root: str) -> None:
        self.root = os.path.normpath(root)
        self._level: dict[str, str | None] = {}  # mejor imagen de cada carpeta, sin subir
        self._cover: dict[str, str | None] = {}  # resultado subiendo

    def cover_for(self, folder: str) -> str | None:
        folder = os.path.normpath(folder)
        if folder not in self._cover:
            cover = self._best_in(folder)
            if cover is None and folder != self.root:
                parent = os.path.dirname(folder)
                inside = os.path.commonpath([parent, self.root]) == self.root
                if parent != folder and inside:
                    cover = self.cover_for(parent)
            self._cover[folder] = cover
        return self._cover[folder]

    def _best_in(self, folder: str) -> str | None:
        if folder in self._level:
            return self._level[folder]
        names = {_norm(os.path.basename(folder))}
        rel = os.path.relpath(folder, self.root)
        if rel != ".":
            names.add(_norm(rel.split(os.sep)[0]))  # carpeta del pack
        names.discard("")
        preferred, others = [], []
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if (Path(entry.name).suffix.lower() not in IMAGE_EXTENSIONS
                            or not entry.is_file()):
                        continue
                    stem = _norm(Path(entry.name).stem)
                    size = entry.stat().st_size
                    named = stem in names or stem.startswith(COVER_WORDS)
                    (preferred if named else others).append((size, entry.path))
        except OSError:
            pass
        best = max(preferred or others, default=None)
        self._level[folder] = best[1] if best else None
        return self._level[folder]


def _src(value, source: str) -> str | None:
    return source if value is not None else None


def scan_root(conn: sqlite3.Connection, root: str, progress: Progress | None = None,
              should_stop: Callable[[], bool] = lambda: False) -> int:
    """Indexa los archivos nuevos o modificados de `root` y borra los que ya no existen.
    Devuelve cuántos archivos quedaron pendientes de análisis."""
    existing = {
        r["path"]: (r["mtime"], r["size"], r["cover"])
        for r in conn.execute("SELECT path, mtime, size, cover FROM samples WHERE root = ?",
                              (root,))
    }
    covers = CoverFinder(root)
    seen: set[str] = set()
    changed = 0
    for dirpath, _dirs, filenames in os.walk(root):
        if should_stop():
            return changed
        for filename in filenames:
            if Path(filename).suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            path = os.path.join(dirpath, filename)
            try:
                st = os.stat(path)
            except OSError:
                continue
            seen.add(path)
            old = existing.get(path)
            cover = covers.cover_for(dirpath)
            if old and old[2] != cover:  # portada nueva, cambiada o borrada
                conn.execute("UPDATE samples SET cover = ? WHERE path = ?", (cover, path))
            if old and old[:2] == (st.st_mtime, st.st_size):
                continue
            _index_file(conn, root, path, st)
            if not old:
                conn.execute("UPDATE samples SET cover = ? WHERE path = ?", (cover, path))
            changed += 1
            if progress and changed % 200 == 0:
                conn.commit()
                progress(f"Indexando {root}: {changed} archivos nuevos…")
    for path in set(existing) - seen:
        conn.execute("DELETE FROM samples WHERE path = ?", (path,))
    conn.commit()
    return changed


def _index_file(conn: sqlite3.Connection, root: str, path: str, st: os.stat_result) -> None:
    parsed = parse_path(path, root)
    acid = read_acid(path)
    bpm, bpm_source = parsed.bpm, _src(parsed.bpm, "name")
    kind, kind_source = parsed.kind, _src(parsed.kind, "name")
    if acid:
        if acid.tempo:
            bpm, bpm_source = acid.tempo, "meta"
        if acid.oneshot and kind is None:
            kind, kind_source = "oneshot", "meta"
    conn.execute(
        """
        INSERT INTO samples (path, root, name, folder, size, mtime, kind, kind_source,
                             bpm, bpm_source, key, key_source, instrument, instrument_source,
                             analyzed, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
        ON CONFLICT(path) DO UPDATE SET
            size = excluded.size, mtime = excluded.mtime,
            kind = excluded.kind, kind_source = excluded.kind_source,
            bpm = excluded.bpm, bpm_source = excluded.bpm_source,
            key = excluded.key, key_source = excluded.key_source,
            instrument = excluded.instrument, instrument_source = excluded.instrument_source,
            duration = NULL, analyzed = 0, error = NULL
        """,
        (
            path, root, Path(path).name, os.path.relpath(os.path.dirname(path), root),
            st.st_size, st.st_mtime, kind, kind_source, bpm, bpm_source,
            parsed.key, _src(parsed.key, "name"), parsed.instrument,
            _src(parsed.instrument, "name"),
        ),
    )
    db.apply_user_fields(conn, path)


def _analyze_job(sample: dict) -> dict:
    """Corre en un proceso aparte (librosa es pesado y no libera el GIL)."""
    from sample_scout.analyzer import analyze

    instrument = sample["instrument"]

    def need(field: str) -> bool:  # un dato vacío a propósito por el usuario no se estima
        return sample[field] is None and sample[f"{field}_source"] != "user"

    try:
        result = analyze(
            sample["path"],
            need_bpm=need("bpm"),
            need_key=need("key") and instrument not in DRUM_INSTRUMENTS,
            need_instrument=need("instrument"),
            kind_hint=sample["kind"],
        )
        return {"id": sample["id"], "result": result}
    except Exception as exc:  # archivos corruptos o formatos raros
        return {"id": sample["id"], "error": f"{type(exc).__name__}: {exc}"}


def _apply(conn: sqlite3.Connection, sample: dict, job: dict) -> None:
    if "error" in job:
        conn.execute("UPDATE samples SET analyzed = 1, error = ? WHERE id = ?",
                     (job["error"], sample["id"]))
        return
    r = job["result"]
    # La fila actual y no la del arranque del análisis: el usuario pudo editarla mientras tanto.
    current = conn.execute("SELECT * FROM samples WHERE id = ?", (sample["id"],)).fetchone()
    s = dict(current) if current else dict(sample)
    for field in ("kind", "bpm", "key", "instrument"):
        if s[f"{field}_source"] == "user":
            continue
        if s[field] is None and r.get(field) is not None:
            s[field], s[f"{field}_source"] = r[field], "audio"
    # Un one-shot no tiene tempo; un número en el nombre era solo una numeración.
    if s["kind"] == "oneshot" and s["bpm_source"] == "name":
        s["bpm"] = s["bpm_source"] = None
    # La tonalidad estimada de una batería es ruido.
    if s["instrument"] in DRUM_INSTRUMENTS and s["key_source"] == "audio":
        s["key"] = s["key_source"] = None
    conn.execute(
        """
        UPDATE samples SET duration = ?, kind = ?, kind_source = ?, bpm = ?, bpm_source = ?,
            key = ?, key_source = ?, instrument = ?, instrument_source = ?, analyzed = 1,
            error = NULL
        WHERE id = ?
        """,
        (r.get("duration"), s["kind"], s["kind_source"], s["bpm"], s["bpm_source"], s["key"],
         s["key_source"], s["instrument"], s["instrument_source"], s["id"]),
    )


def analyze_pending(conn: sqlite3.Connection, progress: Progress | None = None,
                    should_stop: Callable[[], bool] = lambda: False,
                    workers: int | None = None) -> int:
    """Analiza en paralelo (un proceso por núcleo menos uno) todo lo que tenga analyzed = 0 y
    guarda cada resultado apenas llega. Devuelve cuántos procesó. Un archivo que falla queda
    analizado con su error en la columna `error`, para no reintentarlo en cada arranque."""
    pending = [dict(r) for r in conn.execute("SELECT * FROM samples WHERE analyzed = 0")]
    if not pending:
        return 0
    by_id = {s["id"]: s for s in pending}
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_analyze_job, s) for s in pending]
        for future in as_completed(futures):
            if should_stop():
                for f in futures:
                    f.cancel()
                break
            job = future.result()
            _apply(conn, by_id[job["id"]], job)
            done += 1
            if done % 25 == 0 or done == len(pending):
                conn.commit()
                if progress:
                    progress(f"Analizando audio: {done}/{len(pending)}")
    conn.commit()
    return done
