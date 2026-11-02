from sample_scout.parser import parse_path

ROOT = r"C:\Samples"


def p(rel: str):
    return parse_path(rf"{ROOT}\{rel}", ROOT)


def test_nombre_de_pack_comercial():
    r = p(r"Techno Vol 2\Loops\TV2_124_Fm_Bass_Loop_03.wav")
    assert (r.bpm, r.key, r.instrument, r.kind) == (124, "Fm", "bass", "loop")


def test_bpm_explicito_y_bemoles():
    r = p(r"Pack\Synth_128bpm_Ebmin_lead.wav")
    assert (r.bpm, r.key, r.instrument) == (128, "D#m", "synth")


def test_instrumento_desde_carpeta_mas_profunda():
    r = p(r"Bass House Vol 1\Drums\Kicks\001.wav")
    assert r.instrument == "kick"


def test_genero_no_confunde_instrumento():
    r = p(r"Drum and Bass Essentials\Pads\Dark 01.wav")
    assert r.instrument == "pad"


def test_numeracion_de_volumen_no_es_bpm():
    r = p(r"Pack\Vol 100 Snare.wav")
    assert r.bpm is None
    assert r.instrument == "snare"


def test_letra_sola_no_es_tonalidad():
    r = p(r"Pack\A Kick Sample.wav")
    assert r.key is None


def test_letra_sola_pegada_a_bpm_si_es_tonalidad():
    r = p(r"Pack\120 C Piano.wav")
    assert (r.bpm, r.key, r.instrument) == (120, "C", "keys")


def test_one_shot_y_hi_hat_separados():
    r = p(r"Mis cosas\hi hat one shot 3.wav")
    assert (r.instrument, r.kind) == ("hat", "oneshot")


def test_archivo_sin_info():
    r = p(r"grabaciones\audio_2023.wav")
    assert (r.bpm, r.key, r.instrument, r.kind) == (None, None, None, None)
