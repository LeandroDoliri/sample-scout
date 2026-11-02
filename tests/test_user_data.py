import sqlite3
import wave

import pytest

from sample_scout import db, scanner

OLD_SCHEMA = """
CREATE TABLE roots (path TEXT PRIMARY KEY);
CREATE TABLE samples (
    id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, root TEXT NOT NULL, name TEXT NOT NULL,
    folder TEXT NOT NULL, size INTEGER, mtime REAL, duration REAL, kind TEXT, kind_source TEXT,
    bpm REAL, bpm_source TEXT, key TEXT, key_source TEXT, instrument TEXT,
    instrument_source TEXT, analyzed INTEGER NOT NULL DEFAULT 0, error TEXT
);
"""


def _wav(path, seconds=0.1):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * int(8000 * seconds))
    return str(path)


@pytest.fixture
def lib(tmp_path):
    """Base nueva con una carpeta indexada: un loop de bajo a 124 en Am y un kick."""
    root = tmp_path / "lib"
    loop = _wav(root / "Pack" / "Bass Loop 124 Am.wav")
    kick = _wav(root / "Pack" / "Kick 01.wav")
    conn = db.connect(tmp_path / "test.db")
    db.add_root(conn, str(root))
    scanner.scan_root(conn, str(root))
    yield conn, str(root), loop, kick
    conn.close()


def _row(conn, path):
    return db.get_samples(conn, [path])[path]


def test_migra_base_de_la_version_anterior_sin_perder_datos(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(OLD_SCHEMA)
    old.execute("INSERT INTO roots VALUES ('C:\\\\samples')")
    old.execute("INSERT INTO samples (path, root, name, folder, bpm, bpm_source, analyzed) "
                "VALUES ('C:\\\\samples\\\\a.wav', 'C:\\\\samples', 'a.wav', '.', 120, 'name', 1)")
    old.commit()
    old.close()

    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert db.list_roots(conn) == ["C:\\\\samples"]
    [row] = db.search(conn)
    assert (row["bpm"], row["bpm_source"], row["analyzed"]) == (120, "name", 1)
    assert (row["favorite"], row["rating"], row["tags"]) == (0, 0, None)
    db.set_favorite(conn, [row["path"]], True)  # las tablas nuevas funcionan
    assert db.search(conn, favorites=True)[0]["path"] == row["path"]
    conn.close()
    db.connect(path).close()  # migrar dos veces no rompe nada


def test_edicion_manual_gana_y_sobrevive_al_re_escaneo(lib):
    conn, root, loop, _kick = lib
    assert _row(conn, loop)["bpm_source"] == "name"
    db.set_user_field(conn, [loop], "bpm", 125.0)
    db.set_user_field(conn, [loop], "key", "C#m")
    row = _row(conn, loop)
    assert (row["bpm"], row["bpm_source"], row["key"], row["key_source"]) == \
        (125.0, "user", "C#m", "user")

    # Archivo modificado: se vuelve a indexar desde el nombre, pero lo manual sigue ganando.
    conn.execute("UPDATE samples SET mtime = 0 WHERE path = ?", (loop,))
    assert scanner.scan_root(conn, root) == 1
    row = _row(conn, loop)
    assert (row["bpm"], row["bpm_source"], row["key"], row["key_source"]) == \
        (125.0, "user", "C#m", "user")
    assert row["instrument_source"] == "name"


def test_el_analisis_no_pisa_lo_manual(lib):
    conn, _root, loop, kick = lib
    db.set_user_field(conn, [kick], "instrument", "perc")
    db.set_user_field(conn, [loop], "key", None)  # vacío a propósito
    for path, result in ((kick, {"instrument": "kick", "kind": "oneshot", "duration": 0.1}),
                         (loop, {"key": "Gm", "duration": 0.1})):
        sample = _row(conn, path)
        scanner._apply(conn, sample, {"id": sample["id"], "result": result})
    assert (_row(conn, kick)["instrument"], _row(conn, kick)["instrument_source"]) == \
        ("perc", "user")
    assert _row(conn, kick)["kind_source"] == "audio"  # lo no editado sí se completa
    assert (_row(conn, loop)["key"], _row(conn, loop)["key_source"]) == (None, "user")


def test_restablecer_vuelve_a_lo_automatico(lib):
    conn, root, loop, _kick = lib
    db.set_user_field(conn, [loop], "bpm", 90.0)
    db.clear_user_fields(conn, [loop])
    scanner.scan_root(conn, root)
    row = _row(conn, loop)
    assert (row["bpm"], row["bpm_source"]) == (124, "name")


def test_datos_del_usuario_sobreviven_a_quitar_y_volver_a_agregar_la_carpeta(lib):
    conn, root, loop, kick = lib
    db.set_favorite(conn, [loop], True)
    db.set_rating(conn, [loop, kick], 4)
    db.add_tags(conn, [loop], ["oscuro", " techno "])
    db.set_user_field(conn, [kick], "instrument", "perc")
    coll = db.create_collection(conn, "Tema nuevo")
    db.add_to_collection(conn, coll, [loop, kick])
    db.add_history(conn, kick)

    db.remove_root(conn, root)
    assert db.search(conn) == []
    assert db.list_collections(conn)[0]["n"] == 0  # cuenta solo lo que está en la librería

    db.add_root(conn, root)
    scanner.scan_root(conn, root)
    row = _row(conn, loop)
    assert (row["favorite"], row["rating"], row["tags"]) == (1, 4, "oscuro, techno")
    assert _row(conn, kick)["instrument_source"] == "user"
    assert {r["path"] for r in db.search(conn, collection=coll)} == {loop, kick}
    assert [r["path"] for r in db.search(conn, history=True)] == [kick]


def test_filtros_de_favoritos_estrellas_tags_y_texto(lib):
    conn, _root, loop, kick = lib
    db.set_favorite(conn, [kick], True)
    db.set_rating(conn, [loop], 5)
    db.set_rating(conn, [kick], 2)
    db.add_tags(conn, [kick], ["Gordo"])
    assert [r["path"] for r in db.search(conn, favorites=True)] == [kick]
    assert [r["path"] for r in db.search(conn, min_rating=3)] == [loop]
    assert [r["path"] for r in db.search(conn, tag="Gordo")] == [kick]
    assert [r["path"] for r in db.search(conn, text="gordo")] == [kick]  # el texto busca tags
    assert db.all_tags(conn) == [("Gordo", 1)]
    db.remove_tags(conn, [kick], ["Gordo"])
    assert db.search(conn, text="gordo") == []
    db.set_rating(conn, [kick], 9)
    assert _row(conn, kick)["rating"] == 5


def test_colecciones(lib):
    conn, _root, loop, kick = lib
    a = db.create_collection(conn, "Drums")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_collection(conn, "drums")
    db.rename_collection(conn, a, "Baterías")
    b = db.create_collection(conn, "Bajos")
    db.add_to_collection(conn, a, [kick])
    db.add_to_collection(conn, b, [loop, kick])  # un sample puede estar en varias
    db.add_to_collection(conn, b, [loop])  # repetir no duplica
    assert [(c["name"], c["n"]) for c in db.list_collections(conn)] == \
        [("Bajos", 2), ("Baterías", 1)]
    db.remove_from_collection(conn, b, [kick])
    assert [r["path"] for r in db.search(conn, collection=b)] == [loop]
    db.delete_collection(conn, b)
    assert [c["name"] for c in db.list_collections(conn)] == ["Baterías"]
    assert conn.execute("SELECT COUNT(*) FROM collection_items").fetchone()[0] == 1


def test_historial_en_orden_de_escucha_y_con_limite(lib, monkeypatch):
    conn, _root, loop, kick = lib
    clock = iter(range(1000))
    monkeypatch.setattr(db.time, "time", lambda: next(clock))
    db.add_history(conn, loop)
    db.add_history(conn, kick)
    assert [r["path"] for r in db.search(conn, history=True)] == [kick, loop]
    db.add_history(conn, loop)
    assert [r["path"] for r in db.search(conn, history=True)] == [loop, kick]
    assert [r["path"] for r in db.search(conn, history=True, text="kick")] == [kick]

    monkeypatch.setattr(db, "HISTORY_SIZE", 3)
    for i in range(5):
        db.add_history(conn, f"C:\\otro\\{i}.wav")
    assert conn.execute("SELECT COUNT(*) FROM history").fetchone()[0] == 3
    assert db.history_count(conn) == 0
