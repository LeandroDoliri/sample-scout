import os
import sqlite3
import wave
from pathlib import Path

import numpy as np
import pytest

from clap_signals import SR, reference_signals
from sample_scout import clap, db, scanner

MODEL = Path(os.environ.get("SAMPLE_SCOUT_TEST_MODEL") or clap.model_dir())
needs_model = pytest.mark.skipif(not clap.is_installed(MODEL), reason="modelo no instalado")


def _wav(path, samples: np.ndarray, sr: int = SR):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(samples, -1, 1) * 32000).astype("<i2").tobytes())
    return str(path)


def _vec(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(clap.DIM)
    return v / np.linalg.norm(v)


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    signals = reference_signals()
    paths = [_wav(root / "Pack" / "Kick 01.wav", signals["hit"]),
             _wav(root / "Pack" / "Synth Loop.wav", signals["loop"])]
    conn = db.connect(tmp_path / "test.db")
    db.add_root(conn, str(root))
    scanner.scan_root(conn, str(root))
    yield conn, str(root), paths
    conn.close()


def test_migra_base_del_esquema_3(tmp_path):
    """Una base de la 0.2.0 (esquema 3) suma la tabla de embeddings sin perder datos."""
    path = tmp_path / "v3.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA.split("-- Embeddings de CLAP")[0])
    old.execute("INSERT INTO samples (path, root, name, folder, bpm, analyzed) "
                "VALUES ('C:/s/a.wav', 'C:/s', 'a.wav', '.', 120, 1)")
    old.execute("INSERT INTO marks VALUES ('C:/s/a.wav', 1, 3)")
    old.execute("PRAGMA user_version = 3")
    old.commit()
    assert "embeddings" not in {r[0] for r in old.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    old.close()

    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    [row] = db.search(conn)
    assert (row["bpm"], row["favorite"], row["rating"]) == (120, 1, 3)
    assert db.embedding_pending(conn, clap.MODEL_ID) == [
        {"path": "C:/s/a.wav", "mtime": None, "size": None}]
    conn.close()


def test_embeddings_por_ruta_se_invalidan_y_sobreviven(lib):
    conn, root, (kick, loop) = lib
    model = clap.MODEL_ID
    pending = db.embedding_pending(conn, model)
    assert [p["path"] for p in pending] == sorted([kick, loop])
    db.save_embeddings(conn, model, [(p["path"], p["mtime"], p["size"],
                                      clap.to_blob(_vec(i))) for i, p in enumerate(pending)])
    assert db.embedding_pending(conn, model) == []
    assert db.embedding_stats(conn, model) == (2, 2)
    paths, blobs = db.load_embeddings(conn, model)
    assert sorted(paths) == sorted([kick, loop]) and all(len(b) == 1024 for b in blobs)

    # Quitar la carpeta y volver a agregarla no obliga a recalcular nada.
    db.remove_root(conn, root)
    assert db.load_embeddings(conn, model) == ([], [])
    db.add_root(conn, root)
    scanner.scan_root(conn, root)
    assert db.embedding_pending(conn, model) == []

    # Si el archivo cambia (mtime / tamaño), el embedding viejo deja de valer.
    _wav(Path(kick), reference_signals()["hit"][: SR // 2])
    os.utime(kick, (1_700_000_000, 1_700_000_000))
    scanner.scan_root(conn, root)
    assert [p["path"] for p in db.embedding_pending(conn, model)] == [kick]
    assert db.load_embeddings(conn, model)[0] == [loop]

    # Un audio que no se pudo leer (b"") no vuelve a quedar pendiente ni aparece al buscar.
    [p] = db.embedding_pending(conn, model)
    db.save_embeddings(conn, model, [(p["path"], p["mtime"], p["size"], b"")])
    assert db.embedding_pending(conn, model) == []
    assert db.load_embeddings(conn, model)[0] == [loop]
    assert db.embedding_stats(conn, model) == (2, 2)

    before = db.embedding_version(conn, model)
    db.clear_embeddings(conn, model)
    assert db.embedding_version(conn, model) != before
    assert len(db.embedding_pending(conn, model)) == 2


def test_index_ordena_por_coseno():
    base = _vec(0)
    near = base + 0.1 * _vec(1)
    far = _vec(2)
    paths = ["a", "b", "c"]
    index = clap.Index(paths, [clap.to_blob(v / np.linalg.norm(v)) for v in (base, near, far)])
    assert "a" in index and "z" not in index and len(index) == 3
    similar = index.similar("a", 10)
    assert list(similar) == ["b", "c"]  # sin él mismo, del más al menos parecido
    assert similar["b"] > 0.95 > similar["c"]
    assert list(index.scores(base, 1)) == ["a"]
    assert index.similar("z", 5) == {}
    assert clap.Index([], []).scores(base, 5) == {}


@needs_model
def test_embed_pending_con_el_modelo(lib, tmp_path):
    """De punta a punta: un solo proceso, lotes, un archivo roto queda como b"" y lo parecido
    queda primero."""
    conn, root, (kick, loop) = lib
    signals = reference_signals()
    rng = np.random.default_rng(5)
    kick2 = _wav(Path(root) / "Pack" / "Kick 02.wav",
                 0.9 * signals["hit"] + 0.01 * rng.standard_normal(signals["hit"].size))
    broken = Path(root) / "Pack" / "Roto.wav"
    broken.write_bytes(b"RIFF....WAVEbasura")
    scanner.scan_root(conn, root)
    messages = []
    done = scanner.embed_pending(conn, str(MODEL), clap.MODEL_ID, messages.append, threads=2)
    assert done == 4
    assert messages[-1] == "IA: escuchando samples 4/4"
    assert db.embedding_pending(conn, clap.MODEL_ID) == []
    index = clap.Index(*db.load_embeddings(conn, clap.MODEL_ID))
    assert str(broken) not in index and len(index) == 3
    assert list(index.similar(kick, 2)) == [kick2, loop]
    assert scanner.embed_pending(conn, str(MODEL), clap.MODEL_ID) == 0  # nada pendiente
