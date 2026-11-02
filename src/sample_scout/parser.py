"""Extrae BPM, tonalidad, instrumento y tipo a partir de la ruta del archivo.

Es la fuente más barata y, en packs comerciales, la más confiable: casi todos
nombran los archivos como `Pack_124_Fm_Bass_Loop_03.wav`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLATS = {"db": "C#", "eb": "D#", "gb": "F#", "ab": "G#", "bb": "A#", "cb": "B", "fb": "E"}

# Categorías canónicas -> sinónimos que aparecen en nombres de archivos y carpetas.
INSTRUMENTS: dict[str, set[str]] = {
    "kick": {"kick", "kicks", "kik", "bd", "bassdrum", "bassdrums"},
    "snare": {"snare", "snares", "snr", "sd"},
    "clap": {"clap", "claps", "clp"},
    "hat": {"hat", "hats", "hihat", "hihats", "hh", "openhat", "closedhat", "ohh", "chh"},
    "cymbal": {"crash", "crashes", "ride", "rides", "cymbal", "cymbals", "splash", "china"},
    "perc": {
        "perc", "percs", "percussion", "shaker", "shakers", "tom", "toms", "conga", "congas",
        "bongo", "bongos", "rim", "rimshot", "rimshots", "tamb", "tambourine", "cowbell",
        "clave", "claves", "snap", "snaps",
    },
    "drums": {
        "drum", "drums", "beat", "beats", "break", "breaks", "breakbeat", "breakbeats",
        "top", "tops", "toploop", "toploops", "groove", "grooves", "fill", "fills",
    },
    "bass": {"bass", "basses", "bassline", "basslines", "sub", "subs", "subbass", "808", "808s", "reese"},
    "synth": {
        "synth", "synths", "lead", "leads", "pluck", "plucks", "arp", "arps", "stab", "stabs",
        "chord", "chords", "seq", "sequence", "sequences",
    },
    "keys": {"keys", "piano", "pianos", "rhodes", "organ", "organs", "epiano"},
    "pad": {"pad", "pads", "atmos", "atmosphere", "atmospheres", "drone", "drones", "texture", "textures"},
    "vocal": {
        "vocal", "vocals", "vox", "voice", "voices", "acapella", "acapellas", "acappella",
        "chant", "chants", "adlib", "adlibs", "phrase", "phrases",
    },
    "fx": {
        "fx", "sfx", "riser", "risers", "uplifter", "uplifters", "downlifter", "downlifters",
        "sweep", "sweeps", "impact", "impacts", "whoosh", "noise", "transition", "transitions",
        "foley", "reverse",
    },
    "guitar": {"guitar", "guitars", "gtr"},
    "strings": {"string", "strings", "violin", "violins", "cello", "orchestral"},
    "brass": {"brass", "horn", "horns", "trumpet", "trumpets", "sax"},
}

INSTRUMENT_LABELS = {
    "kick": "Kick", "snare": "Snare", "clap": "Clap", "hat": "Hi-hat", "cymbal": "Platillo",
    "perc": "Percusión", "drums": "Batería", "bass": "Bajo", "synth": "Synth", "keys": "Teclados",
    "pad": "Pad", "vocal": "Voz", "fx": "FX", "guitar": "Guitarra", "strings": "Cuerdas",
    "brass": "Vientos",
}

# Instrumentos donde la tonalidad no tiene sentido.
DRUM_INSTRUMENTS = {"kick", "snare", "clap", "hat", "cymbal", "perc", "drums"}

_SYNONYM = {word: canon for canon, words in INSTRUMENTS.items() for word in words}
_LOOP_WORDS = {"loop", "loops"}
_ONESHOT_WORDS = {"oneshot", "oneshots", "shot", "shots", "hit", "hits"}
# Géneros que contienen nombres de instrumentos y confunden la clasificación.
_GENRES = ["drum and bass", "drum n bass", "drum & bass", "drum'n'bass", "drumnbass",
           "bass house", "future bass", "bass music", "breakbeat hardcore"]

_SPLIT = re.compile(r"[\s_\-\.\(\)\[\]\{\},&+~=]+")
_WORDS = re.compile(r"[a-z]+|\d+")
_KEY = re.compile(r"^([a-g])(#|b|sharp|flat)?(m|min|minor|maj|major)?$")
_BPM = re.compile(r"^(\d{2,3}(?:\.\d+)?)bpm$")


@dataclass
class ParsedPath:
    """Lo que se pudo deducir de la ruta. None = no se encontró (lo completa el análisis de audio)."""

    bpm: float | None = None
    key: str | None = None
    instrument: str | None = None
    kind: str | None = None  # "loop" | "oneshot"


def _strip_genres(text: str) -> str:
    low = text.lower()
    for genre in _GENRES:
        low = low.replace(genre, " ")
    return low


def _words(text: str) -> list[str]:
    """Palabras en minúscula, separando letras de números (`kick01` -> kick, 01)."""
    out: list[str] = []
    for raw in _SPLIT.split(_strip_genres(text)):
        out.extend(_WORDS.findall(raw))
    return out


def _find_instrument(words: list[str]) -> str | None:
    # Primero pares pegados ("bass drum" -> bassdrum, "hi hat" -> hihat).
    for a, b in zip(words, words[1:]):
        if a + b in _SYNONYM:
            return _SYNONYM[a + b]
    for word in words:
        if word in _SYNONYM:
            return _SYNONYM[word]
    return None


def _find_kind(words: list[str]) -> str | None:
    for a, b in zip(words, words[1:]):
        if a == "one" and b in {"shot", "shots"}:
            return "oneshot"
    for word in words:
        if word in _LOOP_WORDS:
            return "loop"
        if word in _ONESHOT_WORDS:
            return "oneshot"
    return None


def normalize_key(note: str, accidental: str | None, mode: str | None) -> str:
    """Nombre canónico de la tonalidad: siempre con sostenidos y "m" para menor
    ("eb" + "min" -> "D#m"), así un mismo filtro encuentra "Ebm" y "D#min"."""
    note = note.lower()
    if accidental in ("b", "flat"):
        name = _FLATS.get(note + "b") or NOTES[(NOTES.index(note.upper()) - 1) % 12]
    elif accidental in ("#", "sharp"):
        name = NOTES[(NOTES.index(note.upper()) + 1) % 12]
    else:
        name = note.upper()
    minor = mode in ("m", "min", "minor")
    return name + ("m" if minor else "")


def _find_key(stem: str) -> str | None:
    tokens = [t for t in _SPLIT.split(stem) if t]
    for i, token in enumerate(tokens):
        low = token.lower()
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        m = _KEY.match(low)
        if not m:
            continue
        note, accidental, mode = m.groups()
        if mode is None and nxt in ("minor", "major", "min", "maj"):
            mode = nxt
        if accidental is None and mode is None:
            # Una letra sola ("A", "C") es ambigua: solo vale en mayúscula y pegada a un número.
            neighbours = [tokens[j] for j in (i - 1, i + 1) if 0 <= j < len(tokens)]
            if not (token.isupper() and any(n.replace(".", "").isdigit() for n in neighbours)):
                continue
        return normalize_key(note, accidental, mode)
    return None


def _find_bpm(stem: str) -> float | None:
    tokens = [t.lower() for t in _SPLIT.split(stem) if t]
    # Explícito: "124bpm" o "124 bpm".
    for i, token in enumerate(tokens):
        m = _BPM.match(token)
        if m:
            return float(m.group(1))
        if token == "bpm" and i > 0 and tokens[i - 1].isdigit():
            return float(tokens[i - 1])
    # Implícito: el primer número de 2-3 cifras en rango musical.
    for i, token in enumerate(tokens):
        if token.isdigit() and 70 <= int(token) <= 180:
            if i > 0 and tokens[i - 1] in ("vol", "v", "no", "part", "pt", "ep"):
                continue
            return float(token)
    return None


def parse_path(path: str | Path, root: str | Path | None = None) -> ParsedPath:
    """Analiza nombre de archivo y carpetas. El nombre del archivo manda sobre las carpetas,
    y las carpetas más profundas mandan sobre las de arriba."""
    p = Path(path)
    stem = p.stem
    folders = list(p.parent.parts)
    if root is not None:
        try:
            folders = list(p.parent.relative_to(root).parts)
        except ValueError:
            pass
    folders.reverse()  # de la más profunda a la más alta

    file_words = _words(stem)
    result = ParsedPath(
        bpm=_find_bpm(stem),
        key=_find_key(stem),
        instrument=_find_instrument(file_words),
        kind=_find_kind(file_words),
    )
    for folder in folders:
        words = _words(folder)
        result.instrument = result.instrument or _find_instrument(words)
        result.kind = result.kind or _find_kind(words)
    return result
