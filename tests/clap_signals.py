"""Señales de prueba para comparar el mel espectrograma de `clap.py` con el de transformers.

Las usan tests/test_clap.py y tools/make_clap_fixture.py (que generó el fixture una vez). Son
deterministas: PCG64 da los mismos números en cualquier versión de numpy.
"""

import numpy as np

SR = 48000


def reference_signals() -> dict[str, np.ndarray]:
    """Un golpe corto (1,5 s: se repite hasta llenar los 10 s) y un loop de 10 s justos."""
    rng = np.random.default_rng(1234)
    t = np.arange(int(SR * 1.5)) / SR
    hit = np.sin(2 * np.pi * (50 + 150 * np.exp(-t * 30)) * t) * np.exp(-t * 6)
    hit += 0.3 * rng.standard_normal(t.size) * np.exp(-t * 40)
    t = np.arange(SR * 10) / SR
    loop = sum(0.2 * (2 * ((f * t) % 1) - 1) for f in (220.0, 277.18, 329.63))
    loop *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t)
    hats = (t % 0.25) < 0.02
    loop += 0.2 * rng.standard_normal(t.size) * hats
    return {"hit": hit.astype(np.float32), "loop": (0.8 * loop).astype(np.float32)}


TEXTS = ["kick drum", "a warm ambient pad", "crispy snare", "dark punchy kick"]
