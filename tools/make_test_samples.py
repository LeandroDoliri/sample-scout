"""Genera una librería de prueba con samples sintéticos de resultado conocido.

Uso:
    .venv/Scripts/python tools/make_test_samples.py <carpeta>

Después agregá esa carpeta en la app (o pasala a `--analyze`) y compará con lo esperado:

    archivo                      tipo      BPM   key  instrumento  fuente
    raro/grabacion 7.wav         loop      124   -    -            audio
    raro/cosa1.wav               oneshot   -     -    kick         audio
    raro/cosa2.wav               oneshot   -     -    hat          audio
    raro/idea nueva.wav          loop      -     Am   -            audio (pad: sin tempo)
    Pack_126_Gm_Bass_Loop.wav    loop      126   Gm   bass         nombre

Además deja duplicados para probar la vista "Duplicados": `copias/Kick copiado.wav` (igual a
`raro/cosa1.wav`) y `copias/Bass con tempo.wav` (el mismo audio que el bajo, con un chunk `acid`
agregado, como cuando Ableton guarda el tempo). Tienen que salir dos grupos de dos archivos.

Con `--analyze` además indexa y analiza en una base aparte (<carpeta>/test.db) e imprime el
resultado, sin tocar tu librería.
"""

import shutil
import struct
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100


def kick(seconds=0.4):
    t = np.arange(int(SR * seconds)) / SR
    return np.sin(2 * np.pi * (50 + 120 * np.exp(-t * 30)) * t) * np.exp(-t * 8)


def hat(seconds=0.15):
    x = np.diff(np.diff(np.random.randn(int(SR * seconds)), prepend=0), prepend=0)
    return x / np.abs(x).max() * np.exp(-np.arange(len(x)) / SR * 40)


def write_library(lib: Path) -> None:
    (lib / "raro").mkdir(parents=True, exist_ok=True)
    # Loop de batería de 2 compases a 124 BPM, sin datos en el nombre
    beat = 60 / 124
    length = int(SR * beat * 8)
    y = np.zeros(length)
    for b in range(8):
        k = kick()
        s = int(b * beat * SR)
        y[s:s + len(k)] += k[:length - s]
        h = hat()
        s = int((b + 0.5) * beat * SR)
        y[s:s + len(h)] += 0.3 * h[:length - s]
    sf.write(lib / "raro" / "grabacion 7.wav", y / np.abs(y).max() * 0.9, SR)
    sf.write(lib / "raro" / "cosa1.wav", kick() * 0.9, SR)
    sf.write(lib / "raro" / "cosa2.wav", hat() * 0.9, SR)
    # Pad sostenido en La menor (La, Do, Mi), 8 s: tiene tonalidad pero no tempo
    t = np.arange(SR * 8) / SR
    pad = sum(np.sin(2 * np.pi * f * t) for f in (110, 220, 261.63, 329.63))
    sf.write(lib / "raro" / "idea nueva.wav", pad / np.abs(pad).max() * 0.5, SR)
    # Sample "comercial": todo sale del nombre
    bass = np.sin(2 * np.pi * 98 * np.arange(int(SR * 240 / 126 * 2)) / SR) * 0.5
    sf.write(lib / "Pack_126_Gm_Bass_Loop.wav", bass, SR)
    # Duplicados: una copia exacta con otro nombre y el mismo audio con metadata distinta
    (lib / "copias").mkdir(exist_ok=True)
    shutil.copy(lib / "raro" / "cosa1.wav", lib / "copias" / "Kick copiado.wav")
    tagged = lib / "copias" / "Bass con tempo.wav"
    shutil.copy(lib / "Pack_126_Gm_Bass_Loop.wav", tagged)
    with open(tagged, "r+b") as f:  # chunk acid: 8 beats a 126 BPM
        f.seek(0, 2)
        f.write(b"acid" + struct.pack("<I", 24) + struct.pack("<IHHfIHHf", 0, 60, 0, 0, 8, 4, 4,
                                                             126.0))
        size = f.tell() - 8
        f.seek(4)
        f.write(struct.pack("<I", size))


def analyze(lib: Path) -> None:
    from sample_scout import db, scanner

    conn = db.connect(lib / "test.db")
    db.add_root(conn, str(lib))
    scanner.scan_root(conn, str(lib))
    scanner.analyze_pending(conn)
    for r in db.search(conn):
        print(f"{r['name']:28} {r['kind'] or '-':8} bpm={r['bpm']} ({r['bpm_source']}) "
              f"key={r['key']} ({r['key_source']}) inst={r['instrument']} "
              f"({r['instrument_source']}) err={r['error']}")
    print("Duplicados:")
    for r in db.search(conn, duplicates=True):
        print(f"  {r['content_hash'][:8]} {r['path']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    folder = Path(sys.argv[1])
    write_library(folder)
    print(f"Librería de prueba en {folder}")
    if "--analyze" in sys.argv:
        analyze(folder)
