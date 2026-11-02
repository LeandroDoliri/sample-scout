r"""Genera tests/fixtures/clap_reference.npz con transformers (una sola vez, fuera de la app).

Guarda, para las señales de tests/clap_signals.py, el mel de `ClapFeatureExtractor` y los
embeddings de PyTorch, y los ids del tokenizer de transformers para unos textos. Con eso
tests/test_clap.py controla que el mel portado a librosa, el tokenizer y los ONNX den lo mismo.

Se corre con el venv del spike (torch + transformers; la app no los usa):
    C:\temp\ss-clap\venv\Scripts\python -I tools/make_clap_fixture.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from clap_signals import SR, TEXTS, reference_signals  # noqa: E402

REPO_ID = "laion/clap-htsat-unfused"


def main() -> None:
    import torch
    from transformers import ClapModel, ClapProcessor

    processor = ClapProcessor.from_pretrained(REPO_ID)
    model = ClapModel.from_pretrained(REPO_ID).eval()
    out = {}
    signals = reference_signals()
    for name, y in signals.items():
        feats = processor.feature_extractor([y], sampling_rate=SR, return_tensors="pt")
        out[f"mel_{name}"] = feats["input_features"][0, 0].numpy().astype(np.float16)
        with torch.inference_mode():
            emb = model.get_audio_features(**feats)
        emb = getattr(emb, "pooler_output", emb)
        emb = torch.nn.functional.normalize(emb, dim=-1)
        out[f"audio_{name}"] = emb[0].numpy().astype(np.float32)
    tok = processor.tokenizer(TEXTS, padding=True, return_tensors="np")
    out["text_ids"] = tok["input_ids"].astype(np.int32)
    with torch.inference_mode():
        emb = model.get_text_features(**processor.tokenizer(TEXTS, padding=True,
                                                            return_tensors="pt"))
    emb = getattr(emb, "pooler_output", emb)
    out["text_emb"] = torch.nn.functional.normalize(emb, dim=-1).numpy().astype(np.float32)
    dest = ROOT / "tests" / "fixtures" / "clap_reference.npz"
    np.savez_compressed(dest, **out)
    print(f"{dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
