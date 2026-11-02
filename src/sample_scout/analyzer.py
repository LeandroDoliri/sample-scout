"""Análisis de audio: tipo (loop / one-shot), BPM, tonalidad e instrumento aproximado."""

from __future__ import annotations

import hashlib
import struct

import numpy as np

SR = 22050
MAX_SECONDS = 60  # alcanza para estimar; los archivos largos no se cargan enteros

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Perfiles de tonalidad de Krumhansl-Kessler.
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
KEY_MIN_CORRELATION = 0.6
STRONG_ONSET = 1.5
WAVE_POINTS = 240  # columnas de la forma de onda guardada (un byte cada una)
# Chunks que definen el sonido; el resto (acid, LIST, bext, smpl, ID3…) es metadata.
AUDIO_CHUNKS = {b"WAVE": (b"fmt ", b"data"), b"AIFF": (b"COMM", b"SSND"),
                b"AIFC": (b"COMM", b"SSND")}


def duration_of(path: str) -> float:
    """Duración real en segundos, leyendo solo el encabezado (el audio se carga recortado)."""
    import soundfile as sf

    try:
        return float(sf.info(path).duration)
    except Exception:
        import librosa

        return float(librosa.get_duration(path=path))


def _audio_chunks(f) -> list[tuple[int, int]] | None:
    """(posición, tamaño) de los chunks de audio de un WAV o AIFF, o None si no lo es."""
    header = f.read(12)
    if len(header) < 12 or header[:4] not in (b"RIFF", b"FORM"):
        return None
    wanted = AUDIO_CHUNKS.get(header[8:12])
    if not wanted:
        return None
    endian = "<" if header[:4] == b"RIFF" else ">"
    found = {}
    while True:
        chunk = f.read(8)
        if len(chunk) < 8:
            break
        chunk_id, size = chunk[:4], struct.unpack(endian + "I", chunk[4:])[0]
        if chunk_id in wanted:
            found[chunk_id] = (f.tell(), size)
        f.seek(size + (size & 1), 1)
    return [found[c] for c in wanted] if len(found) == len(wanted) else None


def content_hash(path: str) -> str:
    """Huella del contenido para encontrar duplicados. En WAV y AIFF es solo del formato y las
    muestras de audio, así que dos copias con distinto nombre, carpeta o metadata (tempo de
    Ableton, tags, fechas) dan igual. En los demás formatos es del archivo entero."""
    digest = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        chunks = _audio_chunks(f)
        if chunks is None:
            f.seek(0)
            chunks = [(0, -1)]
        for start, size in chunks:
            f.seek(start)
            remaining = size
            while remaining:
                block = f.read(1 << 20 if remaining < 0 else min(1 << 20, remaining))
                if not block:
                    break
                digest.update(block)
                if remaining > 0:
                    remaining -= len(block)
    return digest.hexdigest()


def waveform_peaks(path: str, points: int = WAVE_POINTS) -> bytes:
    """Forma de onda chica para dibujar: el pico absoluto de cada uno de `points` tramos del
    archivo entero, normalizado al pico del archivo, de 0 a 255 (un byte por tramo)."""
    import soundfile as sf

    peaks = np.zeros(points)
    try:
        frames = sf.info(path).frames
        pos = 0
        for block in sf.blocks(path, blocksize=1 << 16, always_2d=True):
            level = np.abs(block).max(axis=1)
            buckets = (np.arange(pos, pos + len(level)) * points // max(frames, 1)).clip(
                0, points - 1)
            np.maximum.at(peaks, buckets, level)
            pos += len(level)
    except Exception:  # formatos que soundfile no lee: con librosa, a baja resolución
        import librosa

        y, _sr = librosa.load(path, sr=8000, mono=True)
        if y.size:
            buckets = np.arange(y.size) * points // y.size
            np.maximum.at(peaks, buckets, np.abs(y))
    top = peaks.max()
    if top > 0:
        peaks = peaks / top * 255
    return np.round(peaks).astype(np.uint8).tobytes()


def guess_kind(duration: float, onset_count: int) -> str:
    """"oneshot" si es corto o tiene pocos ataques fuertes; si no, "loop"."""
    if duration < 1.5 or (duration < 6 and onset_count <= 2):
        return "oneshot"
    return "loop"


def _fold(tempo: float) -> float:
    """Lleva el tempo al rango 70-180, donde vive casi toda la música (corrige doble / mitad)."""
    while tempo and tempo < 70:
        tempo *= 2
    while tempo > 180:
        tempo /= 2
    return tempo


def estimate_bpm(tempo: float, duration: float, onset_count: int = 99) -> float | None:
    """Ajusta el tempo estimado usando el largo del loop: si dura un número entero de
    compases de 4/4, el BPM que sale del largo es mucho más preciso."""
    tempo = _fold(tempo)
    best: tuple[float, float] | None = None
    for bars in (1, 2, 4, 8, 16, 32):
        from_length = 240.0 * bars / duration
        if not 60 <= from_length <= 200:
            continue
        err = abs(from_length - tempo) / from_length
        if err < 0.04 and (best is None or err < best[0]):
            best = (err, from_length)
    if best:
        bpm = best[1]
    elif onset_count >= 4:
        bpm = tempo
    else:
        return None  # sonido sostenido (pad, drone): un tempo inventado confunde más que ayuda
    return round(bpm) if abs(bpm - round(bpm)) < 0.15 else round(bpm, 1)


def estimate_key(chroma_profile: np.ndarray) -> str | None:
    """Tonalidad ("Am", "F#") que mejor correlaciona con el perfil cromático promedio, comparado
    con los 24 perfiles de Krumhansl-Kessler. None si ninguna llega a KEY_MIN_CORRELATION."""
    if not np.any(chroma_profile):
        return None
    best_corr, best_key = -1.0, None
    for i in range(12):
        for profile, suffix in ((MAJOR, ""), (MINOR, "m")):
            corr = float(np.corrcoef(chroma_profile, np.roll(profile, i))[0, 1])
            if corr > best_corr:
                best_corr, best_key = corr, NOTES[i] + suffix
    return best_key if best_corr >= KEY_MIN_CORRELATION else None


def guess_oneshot_instrument(y: np.ndarray, sr: int, duration: float) -> str | None:
    """Heurística simple para one-shots de batería. Se reemplaza más adelante por un modelo."""
    import librosa

    spectrum = np.abs(librosa.stft(y, n_fft=2048)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    total = spectrum.sum()
    if total <= 0:
        return None
    low_ratio = spectrum[freqs < 150].sum() / total
    centroid = float((freqs[:, None] * spectrum).sum() / total)
    if low_ratio > 0.5:
        return "kick" if duration < 1.0 else "bass"
    if centroid > 5000:
        return "hat"
    if duration < 1.5:
        return "perc"
    return None


def analyze(path: str, need_bpm: bool = True, need_key: bool = True,
            need_instrument: bool = True, kind_hint: str | None = None) -> dict:
    """Analiza un archivo y devuelve las claves que pudo estimar: duration siempre, y kind, bpm,
    key e instrument cuando corresponde. Los need_* evitan calcular lo que ya se sabe por el
    nombre o la metadata; kind_hint usa el tipo ya conocido en lugar de estimarlo."""
    import warnings

    import librosa

    # librosa avisa en cada one-shot cortito que la ventana es más larga que la señal.
    warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
    duration = duration_of(path)
    y, sr = librosa.load(path, sr=SR, mono=True, duration=MAX_SECONDS)
    result: dict = {"duration": duration}
    if y.size == 0 or not np.any(y):
        return result

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    # onset_detect normaliza la envolvente y encuentra "ataques" hasta en un pad. La envolvente
    # está en escala logarítmica (no depende del volumen), así que un umbral absoluto separa
    # golpes reales de las fluctuaciones de un sonido sostenido.
    onsets = onsets[onset_env[onsets] >= STRONG_ONSET]
    kind = kind_hint or guess_kind(duration, len(onsets))
    result["kind"] = kind

    if kind == "loop" and need_bpm:
        tempo = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=onset_env, sr=sr))[0])
        if tempo > 0:
            result["bpm"] = estimate_bpm(tempo, duration, len(onsets))

    if kind == "oneshot" and need_instrument:
        result["instrument"] = guess_oneshot_instrument(y, sr, duration)

    if need_key:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        result["key"] = estimate_key(chroma.mean(axis=1))
    return result
