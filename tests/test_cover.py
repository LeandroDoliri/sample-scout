import os

from sample_scout import db, scanner
from sample_scout.scanner import CoverFinder


def _file(path, size=10):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return str(path)


def test_usa_la_imagen_mas_cercana_subiendo(tmp_path):
    root = tmp_path / "lib"
    pack_cover = _file(root / "Techno Vol 2" / "cover.jpg")
    loops_cover = _file(root / "Techno Vol 2" / "Loops" / "Bass" / "art.png")
    finder = CoverFinder(str(root))
    assert finder.cover_for(str(root / "Techno Vol 2" / "Loops" / "Bass")) == loops_cover
    assert finder.cover_for(str(root / "Techno Vol 2" / "Loops" / "Drums")) == pack_cover
    assert finder.cover_for(str(root / "Techno Vol 2")) == pack_cover


def test_prefiere_nombre_de_portada_y_si_no_la_mas_grande(tmp_path):
    root = tmp_path / "lib"
    _file(root / "A" / "promo banner.jpg", size=5000)
    cover = _file(root / "A" / "Cover_1000x1000.JPG", size=100)
    _file(root / "B" / "chica.png", size=100)
    big = _file(root / "B" / "grande.webp", size=900)
    # Una imagen con el nombre del pack cuenta como portada, aunque sea más chica.
    _file(root / "Deep House Pack" / "otra.jpg", size=900)
    named = _file(root / "Deep House Pack" / "deep_house_pack.png", size=10)
    finder = CoverFinder(str(root))
    assert finder.cover_for(str(root / "A")) == cover
    assert finder.cover_for(str(root / "B")) == big
    assert finder.cover_for(str(root / "Deep House Pack" / "Kicks")) == named


def test_no_sube_mas_arriba_de_la_raiz_ni_toma_otros_archivos(tmp_path):
    _file(tmp_path / "cover.jpg")  # afuera de la raíz
    root = tmp_path / "lib"
    _file(root / "Pack" / "notas.txt")
    _file(root / "Pack" / "cover.jpg.asd")
    (root / "Pack" / "cover.png").mkdir(parents=True)  # una carpeta con nombre de imagen
    assert CoverFinder(str(root)).cover_for(str(root / "Pack")) is None


def test_el_escaneo_guarda_la_ruta_y_la_actualiza(tmp_path):
    root = tmp_path / "lib"
    sample = _file(root / "Pack" / "Loops" / "Bass Loop 124.wav")
    conn = db.connect(tmp_path / "test.db")
    scanner.scan_root(conn, str(root))
    assert db.search(conn)[0]["cover"] is None

    cover = _file(root / "Pack" / "artwork.jpg")
    scanner.scan_root(conn, str(root))  # el sample no cambió, la portada sí
    assert db.search(conn)[0]["cover"] == cover

    os.remove(cover)
    scanner.scan_root(conn, str(root))
    assert db.get_samples(conn, [sample])[sample]["cover"] is None
    conn.close()
