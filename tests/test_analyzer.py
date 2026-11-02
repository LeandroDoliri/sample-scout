from sample_scout.analyzer import estimate_bpm, guess_kind


def test_corrige_mitad_de_tempo_con_el_largo_del_loop():
    # 2 compases a 124 BPM = 3.871 s; el detector suele devolver 62.
    assert estimate_bpm(62.0, 3.871) == 124


def test_tempo_preciso_desde_el_largo():
    assert estimate_bpm(127.4, 240 * 4 / 126) == 126


def test_sin_compases_enteros_usa_el_detector():
    assert estimate_bpm(98.0, 5.3) == 98


def test_sonido_sostenido_no_inventa_tempo():
    assert estimate_bpm(107.7, 7.3, onset_count=1) is None


def test_tipo():
    assert guess_kind(0.4, 1) == "oneshot"
    assert guess_kind(3.9, 1) == "oneshot"
    assert guess_kind(3.9, 16) == "loop"
