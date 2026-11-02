"""Huella del contenido (duplicados), forma de onda y filtro por duración."""

import os
import shutil
import sqlite3
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

from sample_scout import analyzer, db, scanner


def _wav(path, freq=440.0, seconds=0.2, rate=8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(rate * seconds)) / rate
    y = (np.sin(2 * np.pi * freq * t) * np.linspace(1, 0, t.size) * 20000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(y.tobytes())
    return str(path)


def _add_acid_chunk(path):
    """Suma un chunk `acid` al final (como hace Ableton al guardar el tempo): cambia el archivo
    pero no el audio."""
    with open(path, "r+b") as f:
        f.seek(0, 2)
        f.write(b"acid" + struct.pack("<I", 24) + bytes(24))
        size = f.tell() - 8
        f.seek(4)
        f.write(struct.pack("<I", size))


def _analyze(conn):
    """Lo mismo que analyze_pending pero sin procesos ni librosa: solo huella y onda."""
    for r in conn.execute("SELECT * FROM samples WHERE peaks IS NULL").fetchall():
        sample = dict(r)
        scanner._apply(conn, sample, {"id": sample["id"],
                                      "extras": scanner._fingerprint(sample["path"])})
    conn.commit()


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    a = _wav(root / "Pack A" / "Kick 01.wav", freq=60)
    b = root / "Pack B" / "otro nombre.wav"
    b.parent.mkdir(parents=True)
    shutil.copy(a, b)  # copia exacta, en otra carpeta y con otro nombre
    c = _wav(root / "Pack A" / "Hat.wav", freq=3000, seconds=1.0)
    conn = db.connect(tmp_path / "test.db")
    db.add_root(conn, str(root))
    scanner.scan_root(conn, str(root))
    yield conn, str(root), a, str(b), c
    conn.close()


def test_huella_ignora_metadata_pero_no_el_audio(tmp_path):
    a = _wav(tmp_path / "a.wav")
    b = tmp_path / "b.wav"
    shutil.copy(a, b)
    _add_acid_chunk(str(b))
    assert os.path.getsize(a) != os.path.getsize(b)
    assert analyzer.content_hash(a) == analyzer.content_hash(str(b))
    c = _wav(tmp_path / "c.wav", freq=441)
    assert analyzer.content_hash(a) != analyzer.content_hash(c)
    other = tmp_path / "x.mp3"  # formato sin chunks conocidos: hash del archivo entero
    other.write_bytes(b"no es audio")
    assert len(analyzer.content_hash(str(other))) == 32


def test_forma_de_onda(tmp_path):
    peaks = analyzer.waveform_peaks(_wav(tmp_path / "a.wav", seconds=1.0))
    assert len(peaks) == analyzer.WAVE_POINTS
    assert max(peaks) == 255  # normalizada al pico del archivo
    assert peaks[0] > peaks[-1]  # el tono se apaga de a poco
    silence = tmp_path / "silencio.wav"
    with wave.open(str(silence), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes(4 * 800))
    assert analyzer.waveform_peaks(str(silence)) == bytes(analyzer.WAVE_POINTS)


def test_duplicados_agrupados_y_ocultos(lib):
    conn, _root, a, b, c = lib
    assert db.duplicate_count(conn) == 0  # sin analizar todavía no se sabe
    _analyze(conn)
    assert db.duplicate_count(conn) == 2
    dups = db.search(conn, duplicates=True)
    assert {r["path"] for r in dups} == {a, b}
    assert all(r["copies"] == 2 for r in dups)
    assert db.copies_of(conn, a) == [b]
    assert db.copies_of(conn, c) == []
    # Ocultar duplicados: uno por grupo, el primero que pasa los demás filtros.
    assert [r["path"] for r in db.search(conn, hide_duplicates=True)] == [c, a]
    assert [r["path"] for r in db.search(conn, hide_duplicates=True, text="otro")] == [b]


def test_onda_y_huella_se_invalidan_si_cambia_el_archivo(lib):
    conn, root, a, b, _c = lib
    _analyze(conn)
    old = db.get_samples(conn, [b])[b]
    assert old["peaks"] and old["content_hash"]
    assert scanner.scan_root(conn, root) == 0  # sin cambios no se recalcula nada
    assert db.get_samples(conn, [b])[b]["peaks"] == old["peaks"]

    _wav(Path(b), freq=1000, seconds=0.5)  # el archivo cambió
    os.utime(b, (1, 1))
    assert scanner.scan_root(conn, root) == 1
    row = db.get_samples(conn, [b])[b]
    assert (row["peaks"], row["content_hash"]) == (None, None)
    _analyze(conn)
    row = db.get_samples(conn, [b])[b]
    assert row["peaks"] != old["peaks"] and row["content_hash"] != old["content_hash"]
    assert db.duplicate_count(conn) == 0


def test_set_peaks_no_pisa_una_onda_existente(lib):
    conn, _root, a, _b, _c = lib
    db.set_peaks(conn, a, b"\x01" * 4)
    db.set_peaks(conn, a, b"\x02" * 4)
    assert db.get_samples(conn, [a])[a]["peaks"] == b"\x01" * 4


def test_filtro_por_duracion(lib):
    conn, _root, a, b, c = lib
    for path, seconds in ((a, 0.2), (b, 0.2), (c, 1.0)):
        conn.execute("UPDATE samples SET duration = ? WHERE path = ?", (seconds, path))
    assert [r["path"] for r in db.search(conn, duration_min=0.5)] == [c]
    assert {r["path"] for r in db.search(conn, duration_max=0.5)} == {a, b}
    assert db.search(conn, duration_min=0.3, duration_max=0.9) == []


def test_migra_base_del_esquema_2(tmp_path):
    """Una base de la tanda anterior (esquema 2, sin huella ni onda) suma las columnas sin
    perder datos, y el análisis completa la onda de lo ya analizado sin re-analizarlo."""
    path = tmp_path / "v2.db"
    old = sqlite3.connect(path)
    schema = db.SCHEMA.replace(
        "    cover TEXT,  -- ruta de la portada del pack (ver scanner.CoverFinder)\n"
        "    content_hash TEXT,  -- huella del audio para encontrar duplicados "
        "(analyzer.content_hash)\n"
        "    peaks BLOB  -- forma de onda: WAVE_POINTS bytes de 0 a 255 "
        "(analyzer.waveform_peaks)\n", "    cover TEXT\n")
    assert "peaks" not in schema
    old.executescript(schema)
    wav = _wav(tmp_path / "lib" / "Bass Loop.wav")
    old.execute("INSERT INTO samples (path, root, name, folder, bpm, bpm_source, analyzed, "
                "duration) VALUES (?, ?, 'Bass Loop.wav', '.', 120, 'name', 1, 0.2)",
                (wav, str(tmp_path / "lib")))
    old.execute("INSERT INTO marks VALUES (?, 1, 4)", (wav,))
    old.execute("PRAGMA user_version = 2")
    old.commit()
    old.close()

    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    [row] = db.search(conn)
    assert (row["bpm"], row["favorite"], row["rating"], row["copies"]) == (120, 1, 4, 0)
    assert row["peaks"] is None

    sample = dict(conn.execute("SELECT * FROM samples").fetchone())
    job = scanner._analyze_job(sample)  # ya analizado: solo huella y onda
    assert "result" not in job and job["extras"]["peaks"]
    scanner._apply(conn, sample, job)
    row = db.get_samples(conn, [wav])[wav]
    assert len(row["peaks"]) == analyzer.WAVE_POINTS
    assert (row["bpm"], row["bpm_source"], row["analyzed"]) == (120, "name", 1)
    conn.close()
