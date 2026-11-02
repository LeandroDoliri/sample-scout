import hashlib
import http.server
import io
import json
import os
import threading
import zipfile
from pathlib import Path

import numpy as np
import pytest

from clap_signals import TEXTS, reference_signals
from sample_scout import clap

FIXTURE = np.load(Path(__file__).parent / "fixtures" / "clap_reference.npz")
# Carpeta con el modelo instalado para los tests que lo necesitan (si no está, se saltean).
MODEL = Path(os.environ.get("SAMPLE_SCOUT_TEST_MODEL") or clap.model_dir())
needs_model = pytest.mark.skipif(not clap.is_installed(MODEL), reason="modelo no instalado")


def _cos(a, b):
    a, b = np.ravel(a).astype(np.float64), np.ravel(b).astype(np.float64)
    return float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))


@pytest.mark.parametrize("name", ["hit", "loop"])
def test_mel_matches_transformers(name):
    """El mel portado a librosa da lo mismo que ClapFeatureExtractor (el fixture se guardó en
    float16, de ahí la tolerancia absoluta)."""
    mel = clap.mel_features(reference_signals()[name])
    ref = FIXTURE[f"mel_{name}"].astype(np.float32)
    assert mel.shape == ref.shape == (1001, 64)
    assert _cos(mel, ref) >= 0.999
    assert _cos(mel - mel.mean(), ref - ref.mean()) >= 0.999
    assert np.abs(mel - ref).max() < 0.1


def test_mel_of_silence_and_empty():
    assert clap.mel_features(np.zeros(100, dtype=np.float32)).shape == (1001, 64)
    assert clap.mel_features(np.zeros(0, dtype=np.float32)).shape == (1001, 64)


@needs_model
def test_audio_onnx_matches_torch():
    encoder = clap.AudioEncoder(MODEL, threads=2)
    signals = reference_signals()
    emb = encoder.embed([signals["hit"], signals["loop"]])
    assert emb.shape == (2, clap.DIM)
    assert _cos(emb[0], FIXTURE["audio_hit"]) >= 0.999
    assert _cos(emb[1], FIXTURE["audio_loop"]) >= 0.999


@needs_model
def test_tokenizer_and_text_match_transformers():
    encoder = clap.TextEncoder(MODEL, threads=2)
    ids = np.array([e.ids for e in encoder.tokenizer.encode_batch(TEXTS)])
    assert np.array_equal(ids, FIXTURE["text_ids"])
    emb = encoder.embed(TEXTS)
    # El texto va cuantizado a int8: en el spike, coseno medio 0,975 contra fp32.
    sims = [_cos(e, r) for e, r in zip(emb, FIXTURE["text_emb"])]
    assert min(sims) >= 0.9


@needs_model
def test_prompts_file():
    prompts = np.load(MODEL / "prompts.npz", allow_pickle=False)
    assert list(prompts["labels"]) == list(clap.LABELS)
    for kind in clap.PROMPT_KINDS:
        assert prompts[kind].shape == (len(clap.LABELS), clap.DIM)


def test_translate():
    assert clap.translate("kick oscuro con punch") == "kick dark punchy"
    assert clap.translate("Redoblante crujiente") == "snare crispy"
    assert clap.translate("acordes de piano jazzeros") == "chords piano jazzy"
    assert clap.translate("subida para un build up") == "riser for build-up"
    assert clap.translate("voces cálidas") == "vocals warm"
    assert clap.translate("bajo sub profundo") == "bass sub deep"
    assert clap.translate("dark punchy kick") == "dark punchy kick"  # inglés: queda igual
    assert clap.translate("Hi-Hat abierto") == "hi-hat open"


def test_blob_roundtrip():
    vec = clap._normalize(np.random.default_rng(0).standard_normal(clap.DIM))
    blob = clap.to_blob(vec)
    assert len(blob) == 1024
    back = clap.from_blobs([blob, blob])
    assert back.shape == (2, clap.DIM) and back.dtype == np.float32
    assert _cos(back[0], vec) > 0.9999


# --- Instalación ---
def _package(files: dict[str, bytes], model: str = clap.MODEL_ID, extra: dict | None = None):
    manifest = {"model": model, "files": {
        n: {"sha256": hashlib.sha256(d).hexdigest(), "size": len(d)} for n, d in files.items()}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in {**files, **(extra or {})}.items():
            z.writestr(name, data)
        z.writestr("manifest.json", json.dumps(manifest))
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


@pytest.fixture
def server():
    """Servidor HTTP local que entrega lo que se ponga en `content` (con soporte de Range)."""
    state = {"content": b"", "fail": 0, "requests": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.headers.get("Range"))
            if state["fail"]:
                state["fail"] -= 1
                self.send_response(503)
                self.end_headers()
                return
            body, start = state["content"], 0
            if self.headers.get("Range"):
                start = int(self.headers["Range"].split("=")[1].rstrip("-"))
                self.send_response(206)
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(body) - start))
            self.end_headers()
            self.wfile.write(body[start:])

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{httpd.server_port}/{clap.MODEL_ZIP}"
    yield state
    httpd.shutdown()


@pytest.fixture
def models(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_SCOUT_MODELS", str(tmp_path / "models"))
    monkeypatch.setattr(clap.time, "sleep", lambda _s: None)
    return tmp_path / "models"


FILES = {name: f"contenido de {name}".encode() for name in clap.MODEL_FILES}


def test_install_ok(server, models):
    server["content"], digest = _package(FILES)
    seen = []
    folder = clap.install(progress=lambda d, t: seen.append((d, t)), url=server["url"],
                          sha256=digest)
    assert folder == models / clap.MODEL_ID
    assert clap.is_installed(folder)
    assert seen[-1][0] == seen[-1][1] == len(server["content"])
    assert sorted(p.name for p in models.iterdir()) == [clap.MODEL_ID]  # sin restos
    clap.remove()
    assert not clap.is_installed()


def test_install_retries(server, models):
    server["content"], digest = _package(FILES)
    server["fail"] = 2
    clap.install(url=server["url"], sha256=digest, retries=3)
    assert clap.is_installed()


def test_install_gives_up_without_network(server, models):
    server["content"], digest = _package(FILES)
    server["fail"] = 5
    with pytest.raises(clap.ModelError, match="conexión"):
        clap.install(url=server["url"], sha256=digest, retries=2)
    assert not clap.is_installed()


def test_install_resumes_partial_download(server, models):
    server["content"], digest = _package(FILES)
    models.mkdir(parents=True)
    (models / f"{clap.MODEL_ZIP}.part").write_bytes(server["content"][:100])
    clap.install(url=server["url"], sha256=digest)
    assert server["requests"] == ["bytes=100-"]
    assert clap.is_installed()


@pytest.mark.parametrize("case", ["zip_sha", "file_sha", "other_model", "extra_path"])
def test_install_rejects_bad_packages(server, models, case):
    files = dict(FILES)
    if case == "zip_sha":
        server["content"], _ = _package(files)
        digest = "0" * 64
    elif case == "file_sha":
        data, _ = _package(files)
        # Mismo manifest, pero un archivo cambiado: el zip pasa, el archivo no.
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buffer, "w") as z:
            for name in src.namelist():
                z.writestr(name, b"otra cosa" if name == "audio.onnx" else src.read(name))
        server["content"] = buffer.getvalue()
        digest = hashlib.sha256(server["content"]).hexdigest()
    elif case == "other_model":
        server["content"], digest = _package(files, model="otro")
    else:
        server["content"], digest = _package(files, extra={"../afuera.txt": b"x"})
    with pytest.raises(clap.ModelError):
        clap.install(url=server["url"], sha256=digest)
    assert not clap.is_installed()
    assert not (models.parent / "afuera.txt").exists()
    assert [p.name for p in models.iterdir()] == []


def test_install_cancel(server, models):
    server["content"], digest = _package({**FILES, "audio.onnx": os.urandom(1 << 20)})
    with pytest.raises(clap.Cancelled):
        clap.install(url=server["url"], sha256=digest, should_stop=lambda: True)
    assert [p.name for p in models.iterdir()] == []
