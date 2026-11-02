"""Funciones de IA con CLAP (LAION `clap-htsat-unfused`, Apache-2.0): sonidos parecidos y
búsqueda por descripción, todo local.

El modelo no viene con la app: se baja una vez (`install`) de un release propio de GitHub, se
verifica con sha256 y queda en %LOCALAPPDATA%\\SampleScout\\models\\clap-general-v1\\. Son dos
encoders en ONNX (audio en fp32 y texto en int8) que se corren con onnxruntime; el tokenizer es
el de RoBERTa (paquete `tokenizers`) y el mel espectrograma se calcula acá con librosa, igual que
el `ClapFeatureExtractor` de transformers (lo controla tests/test_clap.py). onnxruntime,
tokenizers y librosa se importan adentro de las funciones, para que la ventana arranque rápido.

Sin modelo todo esto queda apagado y la app anda igual.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

import numpy as np

MODEL_ID = "clap-general-v1"
MODEL_TAG = f"models-{MODEL_ID}"  # tag del release (prerelease: nunca "Latest", ver updater)
MODEL_ZIP = f"{MODEL_ID}.zip"
MODEL_URL = os.environ.get(
    "SAMPLE_SCOUT_MODEL_URL",
    f"https://github.com/LeandroDoliri/sample-scout/releases/download/{MODEL_TAG}/{MODEL_ZIP}")
# sha256 del zip publicado (lo imprime tools/build_clap_model.py). Va en el código para que una
# descarga cambiada en el camino o en el servidor no se instale.
MODEL_SHA256 = "ac2d79d12c3c89e32c4cc288fae8dd5f7a5a93d7f14f3433e9d4bdc9ca73f0fa"
MODEL_FILES = ("audio.onnx", "text.int8.onnx", "tokenizer.json", "prompts.npz", "LICENSE")

SR = 48000           # CLAP trabaja a 48 kHz…
MAX_SECONDS = 10     # …con una ventana de 10 s: de lo más largo se usa el principio
N_FFT = 1024
HOP = 480
N_MELS = 64
FMIN, FMAX = 50, 14000
DIM = 512
BATCH = 8
TOKEN_LIMIT = 128

Progress = Callable[[int, int], None]  # (bajado, total) en bytes

# Prompts para clasificar el instrumento (el ensamble del spike): una frase por categoría del
# parser y 6 plantillas promediadas, con {kind} = "loop" u "one-shot". Sus embeddings vienen
# precalculados en prompts.npz (tools/build_clap_model.py), así que clasificar no necesita el
# encoder de texto.
LABELS = {
    "kick": "kick drum", "snare": "snare drum", "clap": "hand clap", "hat": "hi-hat",
    "cymbal": "cymbal crash", "perc": "percussion", "drums": "drum beat", "bass": "bass",
    "synth": "synthesizer", "keys": "piano", "pad": "ambient pad", "vocal": "vocals",
    "fx": "sound effect", "guitar": "guitar", "strings": "string section", "brass": "brass section",
}
TEMPLATES = ("{}", "a recording of a {}", "a {} sample", "the sound of a {}", "a {} {kind}",
             "{} used in electronic music production")
PROMPT_KINDS = {"loop": "loop", "oneshot": "one-shot"}


class ModelError(Exception):
    """El modelo no se pudo bajar o instalar. El mensaje está pensado para el usuario."""


class Cancelled(ModelError):
    """El usuario canceló la descarga."""


# --- Dónde está el modelo ---
def models_dir() -> Path:
    """%LOCALAPPDATA%\\SampleScout\\models, o lo que diga SAMPLE_SCOUT_MODELS (pruebas)."""
    if os.environ.get("SAMPLE_SCOUT_MODELS"):
        return Path(os.environ["SAMPLE_SCOUT_MODELS"])
    base = os.environ.get("LOCALAPPDATA") or Path.home()
    return Path(base) / "SampleScout" / "models"


def model_dir() -> Path:
    return models_dir() / MODEL_ID


def is_installed(folder: Path | None = None) -> bool:
    """Si el modelo está completo (manifest y archivos del tamaño esperado). No recalcula los
    sha256: eso se hace una vez, al instalar."""
    folder = folder or model_dir()
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        files = manifest["files"]
        return all((folder / name).stat().st_size == files[name]["size"] for name in MODEL_FILES)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def remove() -> None:
    """Borra el modelo del disco (se puede volver a bajar)."""
    shutil.rmtree(model_dir(), ignore_errors=True)


# --- Descarga e instalación ---
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, progress: Progress | None,
              should_stop: Callable[[], bool], timeout: float = 30) -> None:
    """Baja `url` a `dest`, siguiendo desde donde quedó si el servidor acepta Range."""
    done = dest.stat().st_size if dest.exists() else 0
    headers = {"User-Agent": "SampleScout"}
    if done:
        headers["Range"] = f"bytes={done}-"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                timeout=timeout) as r:
        if done and r.status != 206:  # no acepta Range: se empieza de nuevo
            done = 0
        total = done + int(r.headers.get("Content-Length") or 0)
        with open(dest, "ab" if done else "wb") as f:
            while chunk := r.read(1 << 18):
                if should_stop():
                    raise Cancelled("descarga cancelada")
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


def _extract(package: Path, dest: Path) -> dict:
    """Descomprime y verifica cada archivo contra el manifest. Devuelve el manifest."""
    with zipfile.ZipFile(package) as z:
        for name in z.namelist():
            parts = name.replace("\\", "/").split("/")
            if name.startswith(("/", "\\")) or ":" in name or ".." in parts or len(parts) > 1:
                raise ModelError(f"el paquete trae una ruta no permitida: {name}")
        z.extractall(dest)
    try:
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        files = manifest["files"]
    except (OSError, ValueError, KeyError):
        raise ModelError("el paquete no trae un manifest.json válido")
    if manifest.get("model") != MODEL_ID:
        raise ModelError(f"el paquete es de otro modelo ({manifest.get('model')})")
    present = {p.name for p in dest.iterdir() if p.is_file()} - {"manifest.json"}
    if present != set(files) or not set(MODEL_FILES) <= present:
        raise ModelError("los archivos del paquete no coinciden con el manifest")
    for name, info in files.items():
        if _sha256(dest / name) != str(info["sha256"]).lower():
            raise ModelError(f"{name} está dañado (el sha256 no coincide)")
    return manifest


def install(progress: Progress | None = None, should_stop: Callable[[], bool] = lambda: False,
            log: Callable[[str], None] = lambda _m: None, retries: int = 3,
            url: str | None = None, sha256: str | None = None) -> Path:
    """Baja el zip del modelo (con reintentos), verifica su sha256 y el de cada archivo, y lo
    deja en model_dir(). Lanza Cancelled o ModelError; en ese caso no queda nada a medias."""
    url = url or MODEL_URL
    sha256 = (sha256 or MODEL_SHA256).lower()
    root = models_dir()
    root.mkdir(parents=True, exist_ok=True)
    package = root / f"{MODEL_ZIP}.part"
    for attempt in range(1, retries + 1):
        try:
            _download(url, package, progress, should_stop)
            break
        except Cancelled:
            package.unlink(missing_ok=True)
            raise
        except (OSError, urllib.error.URLError) as exc:
            if attempt == retries:
                raise ModelError("no se pudo bajar el modelo; revisá tu conexión a internet "
                                 f"({exc})") from exc
            log(f"Falló la descarga, reintentando ({attempt}/{retries - 1})…")
            time.sleep(2 * attempt)
    try:
        log("Verificando la descarga…")
        if _sha256(package) != sha256:
            raise ModelError("la descarga llegó dañada (el sha256 no coincide)")
        work = root / f"{MODEL_ID}.new"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()
        try:
            _extract(package, work)
            shutil.rmtree(model_dir(), ignore_errors=True)
            os.replace(work, model_dir())
        finally:
            shutil.rmtree(work, ignore_errors=True)
    finally:
        package.unlink(missing_ok=True)
    return model_dir()


# --- Audio: mel espectrograma igual al de ClapFeatureExtractor (truncation "rand_trunc",
# padding "repeatpad"), sin depender de transformers ---
_MEL_FILTERS: np.ndarray | None = None


def load_audio(path: str) -> np.ndarray:
    """Mono, 48 kHz, los primeros 10 s."""
    import librosa

    y, _ = librosa.load(path, sr=SR, mono=True, duration=MAX_SECONDS)
    return y.astype(np.float32)


def mel_features(waveform: np.ndarray) -> np.ndarray:
    """Log-mel (1001 × 64, en dB) de un audio mono a 48 kHz. Lo corto se repite hasta llenar
    los 10 s y se completa con silencio; de lo largo se toma el principio."""
    import librosa

    global _MEL_FILTERS
    if _MEL_FILTERS is None:
        _MEL_FILTERS = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=N_MELS, fmin=FMIN,
                                           fmax=FMAX, htk=False, norm="slaney")
    n = SR * MAX_SECONDS
    y = np.asarray(waveform, dtype=np.float64)[:n]
    if 0 < len(y) < n:
        y = np.tile(y, n // len(y))
    y = np.pad(y, (0, n - len(y)))
    spec = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP, window="hann", center=True,
                               pad_mode="reflect")) ** 2
    mel = _MEL_FILTERS @ spec
    return (10 * np.log10(np.maximum(mel, 1e-10))).T.astype(np.float32)


def _normalize(x: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.maximum(norm, 1e-12)


def default_threads() -> int:
    """Núcleos − 2, para no trabar la ventana mientras se calculan embeddings."""
    return max(1, (os.cpu_count() or 2) - 2)


def _session(path: Path, threads: int | None):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads or default_threads()
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])


class AudioEncoder:
    """Encoder de audio (fp32, ~1 GB de RAM una vez cargado)."""

    def __init__(self, folder: Path | None = None, threads: int | None = None) -> None:
        self.session = _session((folder or model_dir()) / "audio.onnx", threads)

    def embed(self, waveforms: list[np.ndarray]) -> np.ndarray:
        """Vectores normalizados (n × 512, float32)."""
        feats = np.stack([mel_features(w) for w in waveforms])[:, None]
        out = self.session.run(None, {"input_features": feats})[0]
        return _normalize(out.astype(np.float32))


class TextEncoder:
    """Encoder de texto (int8). Se carga solo cuando se busca por sonido."""

    def __init__(self, folder: Path | None = None, threads: int | None = None,
                 filename: str = "text.int8.onnx") -> None:
        from tokenizers import Tokenizer

        folder = folder or model_dir()
        self.session = _session(folder / filename, threads)
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(TOKEN_LIMIT)
        self.tokenizer.enable_padding(pad_id=1, pad_token="<pad>")

    def embed(self, texts: list[str]) -> np.ndarray:
        enc = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        out = self.session.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        return _normalize(out.astype(np.float32))


def to_blob(vec: np.ndarray) -> bytes:
    """Vector para guardar en la base: float16 (1 KB)."""
    return np.asarray(vec, dtype=np.float16).tobytes()


def from_blobs(blobs: list[bytes]) -> np.ndarray:
    """Matriz float32 (numpy no tiene BLAS para float16: buscar en float16 es 90× más lento)."""
    if not blobs:
        return np.zeros((0, DIM), dtype=np.float32)
    return np.frombuffer(b"".join(blobs), dtype=np.float16).reshape(-1, DIM).astype(np.float32)


# --- Proceso de embeddings (uno solo, ver scanner.embed_pending) ---
_ENCODER: AudioEncoder | None = None


def embed_job(folder: str, threads: int, paths: list[str]) -> list[bytes]:
    """Corre en el proceso de fondo: decodifica y codifica un lote. El encoder queda cargado en
    ese proceso entre lotes y se libera cuando el proceso termina. Un archivo que no se puede
    leer vuelve como b"" (para no reintentarlo hasta que cambie)."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = AudioEncoder(Path(folder), threads)
    waves, ok = [], []
    for path in paths:
        try:
            y = load_audio(path)
        except Exception:
            y = np.zeros(0, dtype=np.float32)
        if y.size and np.any(y):
            waves.append(y)
            ok.append(True)
        else:
            ok.append(False)
    vecs = iter(_ENCODER.embed(waves)) if waves else iter(())
    return [to_blob(next(vecs)) if good else b"" for good in ok]


# --- Búsqueda en español: CLAP solo entiende inglés, así que se traduce antes ---
GLOSSARY = {
    # instrumentos
    "bombo": "kick", "redoblante": "snare", "caja": "snare", "tambor": "drum",
    "bateria": "drums", "palmas": "clap", "palma": "clap", "aplauso": "clap",
    "platillo": "cymbal", "plato": "cymbal", "charles": "hi-hat", "contratiempo": "hi-hat",
    "percusion": "percussion", "bajo": "bass", "sintetizador": "synthesizer",
    "sinte": "synth", "teclado": "keys", "teclados": "keys", "piano": "piano",
    "organo": "organ", "guitarra": "guitar", "cuerda": "strings", "cuerdas": "strings",
    "violin": "violin", "violonchelo": "cello", "chelo": "cello", "vientos": "brass",
    "metales": "brass", "trompeta": "trumpet", "saxo": "saxophone", "flauta": "flute",
    "voz": "vocal", "voces": "vocals", "coro": "choir", "campana": "bell",
    "campanas": "bells", "acorde": "chord", "acordes": "chords", "arpegio": "arpeggio",
    "melodia": "melody", "ritmo": "beat", "golpe": "hit", "subida": "riser",
    "bajada": "downlifter", "barrido": "sweep", "efecto": "effect", "efectos": "effects",
    "ruido": "noise", "textura": "texture", "ambiente": "ambient", "atmosfera": "atmosphere",
    "silbido": "whistle", "risa": "laugh",
    # timbre y carácter
    "oscuro": "dark", "brillante": "bright", "calido": "warm", "frio": "cold",
    "crujiente": "crispy", "seco": "dry", "humedo": "wet", "profundo": "deep",
    "grave": "low", "agudo": "high", "pesado": "heavy", "suave": "soft", "fuerte": "loud",
    "duro": "hard", "sucio": "dirty", "limpio": "clean", "distorsionado": "distorted",
    "saturado": "saturated", "abierto": "open", "cerrado": "closed", "corto": "short",
    "largo": "long", "rapido": "fast", "lento": "slow", "triste": "sad", "alegre": "happy",
    "feliz": "happy", "epico": "epic", "tenebroso": "spooky", "aterrador": "scary",
    "agresivo": "aggressive", "gordo": "fat", "fino": "thin", "metalico": "metallic",
    "acustico": "acoustic", "electrico": "electric", "electronico": "electronic",
    "analogico": "analog", "retro": "retro", "vintage": "vintage", "cortado": "chopped",
    "cortada": "chopped", "reverso": "reversed", "invertido": "reversed",
    "con": "with", "sin": "without", "para": "for", "y": "and", "o": "or",
    "reverberacion": "reverb", "eco": "echo", "jazzero": "jazzy", "jazzeros": "jazzy",
    "funkero": "funky", "sub": "sub", "punch": "punch", "pegada": "punch",
}
# Frases que se traducen juntas (sobre el texto ya sin tildes ni mayúsculas).
PHRASES = {"con punch": "punchy", "con pegada": "punchy", "con cuerpo": "full",
           "hi hat": "hi-hat", "one shot": "one-shot", "build up": "build-up"}
_STOPWORDS = {"de", "del", "el", "la", "los", "las", "un", "una", "unos", "unas", "que", "en",
              "al", "tipo", "estilo", "sonido"}


def _plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word.lower())
                   if unicodedata.category(c) != "Mn")


def translate(query: str) -> str:
    """Pasa una búsqueda en español a inglés con el glosario de producción. Las palabras que no
    conoce (kick, hi-hat, pad, lead…, o ya en inglés) quedan como están."""
    out = []
    text = " ".join(_plain(query).split())
    for phrase, english in PHRASES.items():
        text = f" {text} ".replace(f" {phrase} ", f" {english} ").strip()
    for word in text.split():
        plain = word.strip(".,;:!?¿¡\"'()")
        if not plain or plain in _STOPWORDS:
            continue
        for candidate in (plain, plain[:-1] if plain.endswith("s") else None,
                          plain[:-2] if plain.endswith("es") else None,
                          plain[:-1] + "o" if plain.endswith("a") else None,
                          plain[:-2] + "o" if plain.endswith("as") else None):
            if candidate and candidate in GLOSSARY:
                out.append(GLOSSARY[candidate])
                break
        else:
            out.append(word)
    return " ".join(out)


class Index:
    """Los embeddings de la librería en memoria (float32), para buscar por fuerza bruta: 4 ms
    para 100.000 vectores, no hace falta un índice."""

    def __init__(self, paths: list[str], blobs: list[bytes]) -> None:
        self.paths = paths
        self.matrix = from_blobs(blobs)
        self._row = {p: i for i, p in enumerate(paths)}

    def __contains__(self, path: str) -> bool:
        return path in self._row

    def __len__(self) -> int:
        return len(self.paths)

    def scores(self, query: np.ndarray, top: int, exclude: str | None = None) -> dict[str, float]:
        """Las `top` rutas más parecidas a `query` (un vector normalizado), con su coseno, de
        la más parecida a la menos."""
        if not len(self.paths):
            return {}
        sims = self.matrix @ np.asarray(query, dtype=np.float32)
        if exclude in self._row:
            sims[self._row[exclude]] = -np.inf
        top = min(top, len(sims))
        best = np.argpartition(-sims, top - 1)[:top]
        best = best[np.argsort(-sims[best])]
        return {self.paths[i]: float(sims[i]) for i in best if np.isfinite(sims[i])}

    def similar(self, path: str, top: int) -> dict[str, float]:
        """Los `top` samples que más se parecen a `path` (sin él)."""
        if path not in self._row:
            return {}
        return self.scores(self.matrix[self._row[path]], top, exclude=path)
