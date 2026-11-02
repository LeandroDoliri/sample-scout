import os
import wave

import pytest

from sample_scout import db, folders, scanner


def _wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\0\0" * 800)
    return str(path)


J = os.path.join


def test_build_tree_counts_sorting_and_intermediate_folders():
    roots = [r"C:\libs\Splice", r"C:\libs\vacía"]
    counts = [
        {"root": roots[0], "folder": ".", "n": 1, "cover": None},
        {"root": roots[0], "folder": J("Pack B", "Drums", "Kicks"), "n": 3, "cover": None},
        {"root": roots[0], "folder": J("Pack B", "Drums"), "n": 2, "cover": None},
        {"root": roots[0], "folder": J("pack a", "Loops"), "n": 4, "cover": None},
    ]
    tree = folders.build_tree(roots, counts)
    assert [n.name for n in tree] == ["Splice", "vacía"]
    splice, empty = tree
    assert (splice.direct, splice.total) == (1, 10)
    assert (empty.direct, empty.total, empty.children) == (0, 0, [])
    # Orden sin distinguir mayúsculas; "pack a" no tiene samples propios pero aparece.
    assert [c.name for c in splice.children] == ["pack a", "Pack B"]
    pack_a, pack_b = splice.children
    assert (pack_a.direct, pack_a.total, pack_a.row) == (0, 4, 0)
    assert pack_b.row == 1 and pack_b.parent is splice
    drums = pack_b.children[0]
    assert (drums.direct, drums.total) == (2, 5)
    kicks = drums.children[0]
    assert kicks.folder == J("Pack B", "Drums", "Kicks")
    assert kicks.path == J(roots[0], "Pack B", "Drums", "Kicks")
    assert splice.path == roots[0]
    assert len(list(splice.walk())) == 6


def test_build_tree_puts_cover_on_the_folder_that_has_it():
    root = r"C:\libs\Splice"
    cover = J(root, "Pack", "cover.jpg")
    counts = [  # las subcarpetas heredan la portada del pack al escanear
        {"root": root, "folder": J("Pack", "Drums"), "n": 2, "cover": cover},
        {"root": root, "folder": J("Pack", "Bass"), "n": 1, "cover": cover},
    ]
    splice = folders.build_tree([root], counts)[0]
    pack = splice.children[0]
    assert pack.cover == cover
    assert splice.cover is None
    assert all(c.cover is None for c in pack.children)


def test_build_tree_handles_deep_nesting():
    root = r"C:\deep"
    folder = J(*(f"n{i}" for i in range(60)))
    tree = folders.build_tree([root], [{"root": root, "folder": folder, "n": 7, "cover": None}])
    node = tree[0]
    depth = 0
    while node.children:
        node = node.children[0]
        depth += 1
    assert depth == 60 and node.direct == 7 and tree[0].total == 7


def test_find_by_absolute_path():
    roots = [r"C:\libs\Splice", r"C:\libs\Splice 2"]
    counts = [{"root": roots[0], "folder": J("Pack", "Drums"), "n": 1, "cover": None},
              {"root": roots[1], "folder": "Otro", "n": 1, "cover": None}]
    tree = folders.build_tree(roots, counts)
    assert folders.find(tree, r"c:\LIBS\splice\pack\drums").name == "Drums"
    assert folders.find(tree, roots[1]).root == roots[1]
    assert folders.find(tree, J(roots[1], "Otro")).root == roots[1]
    assert folders.find(tree, J(roots[0], "No existe")) is None
    assert folders.find(tree, r"D:\otra") is None


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "lib"
    files = [
        _wav(root / "suelto.wav"),
        _wav(root / "Pack_1" / "Kick 01.wav"),
        _wav(root / "Pack_1" / "Drums" / "Snare 01.wav"),
        _wav(root / "Pack_1" / "Drums" / "Hats" / "Hat 01.wav"),
        _wav(root / "Pack_10" / "Bass.wav"),  # "Pack_1" no tiene que traer los de "Pack_10"
        _wav(root / "PACK%" / "Pad.wav"),
    ]
    conn = db.connect(tmp_path / "test.db")
    db.add_root(conn, str(root))
    scanner.scan_root(conn, str(root))
    yield conn, str(root), files
    conn.close()


def _names(rows):
    return sorted(r["name"] for r in rows)


def test_search_by_folder_with_and_without_subfolders(lib):
    conn, root, _files = lib
    assert _names(db.search(conn, folder=(root, "Pack_1"))) == [
        "Hat 01.wav", "Kick 01.wav", "Snare 01.wav"]
    assert _names(db.search(conn, folder=(root, "Pack_1"), subfolders=False)) == ["Kick 01.wav"]
    assert _names(db.search(conn, folder=(root, J("Pack_1", "Drums")))) == [
        "Hat 01.wav", "Snare 01.wav"]
    assert _names(db.search(conn, folder=(root, "PACK%"))) == ["Pad.wav"]
    assert len(db.search(conn, folder=(root, "."))) == 6
    assert _names(db.search(conn, folder=(root, "."), subfolders=False)) == ["suelto.wav"]
    assert db.search(conn, folder=(root + "x", ".")) == []


def test_folder_filter_combines_with_other_filters(lib):
    conn, root, _files = lib
    assert _names(db.search(conn, text="snare", folder=(root, "Pack_1"))) == ["Snare 01.wav"]
    assert db.search(conn, text="bass", folder=(root, "Pack_1")) == []
    assert _names(db.search(conn, instrument="kick", folder=(root, "Pack_1"))) == ["Kick 01.wav"]


def test_folder_paths_and_tree_from_db(lib):
    conn, root, files = lib
    assert db.folder_paths(conn, root, "Pack_1") == sorted(files[1:4])
    assert db.folder_paths(conn, root, "Pack_1", subfolders=False) == [files[1]]
    tree = folders.build_tree(db.list_roots(conn), db.folder_counts(conn))
    top = tree[0]
    assert top.total == 6 and top.direct == 1
    assert [c.name for c in top.children] == ["PACK%", "Pack_1", "Pack_10"]
    assert top.children[1].total == 3


def test_migration_to_5_adds_folder_index(tmp_path):
    path = tmp_path / "old.db"
    conn = db.connect(path)
    conn.execute("DROP INDEX idx_samples_folder")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    conn.close()
    conn = db.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION == 5
    indexes = {r["name"] for r in conn.execute("PRAGMA index_list(samples)")}
    assert "idx_samples_folder" in indexes
    plan = " ".join(r[3] for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT root, folder, COUNT(*), MAX(cover) FROM samples "
        "GROUP BY root, folder"))
    assert "idx_samples_folder" in plan
    conn.close()
