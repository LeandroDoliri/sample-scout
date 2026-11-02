"""Lectura de metadata embebida en WAV (chunk `acid`, que escriben Acid, Ableton y muchos packs)."""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass
class AcidInfo:
    """Lo útil del chunk acid: si está marcado como one-shot y su tempo (None si no es confiable)."""

    oneshot: bool
    tempo: float | None


def read_acid(path: str) -> AcidInfo | None:
    """Recorre los chunks RIFF del WAV sin leer el audio. None si no es WAV o no tiene chunk acid.

    Estructura del chunk (24 bytes): flags (uint32, bit 0 = one-shot), nota raíz (uint16),
    2 bytes, float, cantidad de beats (uint32), compás (2 x uint16) y tempo (float).
    """
    if not path.lower().endswith(".wav"):
        return None
    try:
        with open(path, "rb") as f:
            header = f.read(12)
            if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
                return None
            while True:
                chunk = f.read(8)
                if len(chunk) < 8:
                    return None
                chunk_id, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
                if chunk_id == b"acid":
                    data = f.read(min(size, 24))
                    if len(data) < 24:
                        return None
                    flags = struct.unpack("<I", data[:4])[0]
                    beats = struct.unpack("<I", data[12:16])[0]
                    tempo = struct.unpack("<f", data[20:24])[0]
                    # Muchos one-shots traen tempo 120 por defecto: solo vale si hay beats.
                    valid = beats > 0 and 40 <= tempo <= 250 and not flags & 1
                    return AcidInfo(oneshot=bool(flags & 1), tempo=round(tempo, 2) if valid else None)
                f.seek(size + (size & 1), 1)
    except OSError:
        return None
