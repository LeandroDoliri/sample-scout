r"""Arma dist\clap-general-v1.zip, el paquete del modelo que la app baja a demanda.

Entrada: la carpeta con la exportación a ONNX del spike (tools/spike_clap/clapkit.py en la rama
claude/spike-clap-8402dc: `export_onnx('general')` y `quantize('general')`), que trae
`audio.onnx` (fp32), `text.onnx` (fp32), `text.int8.onnx` y `processor\tokenizer.json`.

El zip lleva:
- audio.onnx       encoder de audio en fp32 (int8 es más lento en x64 emulado)
- text.int8.onnx   encoder de texto cuantizado (126 MB en vez de 501, misma precisión final)
- tokenizer.json   tokenizer de RoBERTa, para el paquete `tokenizers`
- prompts.npz      embeddings de los prompts de instrumento (clap.LABELS × clap.TEMPLATES,
                   para loop y one-shot), calculados con el encoder de texto en fp32
- LICENSE          Apache-2.0 (licencia de laion/clap-htsat-unfused) con la atribución
- manifest.json    modelo, origen, licencia y sha256 + tamaño de cada archivo

El zip es reproducible (fechas fijas, orden fijo): con las mismas entradas da el mismo sha256,
que va en `clap.MODEL_SHA256`.

Uso (desde la raíz del repo, con el venv de la app):
    .venv\Scripts\python tools\build_clap_model.py C:\temp\ss-clap\onnx\general apache-2.0.txt

`apache-2.0.txt` es https://www.apache.org/licenses/LICENSE-2.0.txt.

Para probar la descarga sin publicar: `tools/fake_release.py --model` lo sirve en local.
"""

import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from sample_scout import clap  # noqa: E402

SOURCE = "laion/clap-htsat-unfused"
ATTRIBUTION = f"""Sample Scout: modelo {clap.MODEL_ID}

Encoders de audio y texto de {SOURCE} (LAION, https://huggingface.co/{SOURCE}),
exportados a ONNX por Sample Scout (audio en fp32, texto cuantizado a int8). El tokenizer es el
de RoBERTa que acompaña al modelo. Se distribuyen bajo la licencia Apache-2.0, que sigue.

----------------------------------------------------------------------------------------------
"""
DATE = (2026, 11, 2, 0, 0, 0)


def prompt_embeddings(text: "clap.TextEncoder") -> dict[str, np.ndarray]:
    """Para cada tipo, la matriz (16 × 512) con el promedio normalizado de las 6 plantillas."""
    labels = list(clap.LABELS)
    out = {"labels": np.array(labels)}
    for kind, word in clap.PROMPT_KINDS.items():
        mats = [text.embed([tpl.format(clap.LABELS[lab], kind=word) for lab in labels])
                for tpl in clap.TEMPLATES]
        mean = np.mean(mats, axis=0)
        out[kind] = (mean / np.linalg.norm(mean, axis=1, keepdims=True)).astype(np.float32)
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, license_file = Path(sys.argv[1]), Path(sys.argv[2])
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copyfile(src / "audio.onnx", work / "audio.onnx")
        shutil.copyfile(src / "text.int8.onnx", work / "text.int8.onnx")
        shutil.copyfile(src / "processor" / "tokenizer.json", work / "tokenizer.json")
        (work / "LICENSE").write_text(ATTRIBUTION + license_file.read_text(encoding="utf-8"),
                                      encoding="utf-8", newline="\n")
        print("Calculando los embeddings de los prompts (texto fp32)…")
        text = clap.TextEncoder(work, filename=str((src / "text.onnx").resolve()))
        np.savez(work / "prompts.npz", **prompt_embeddings(text))
        del text
        manifest = {
            "model": clap.MODEL_ID, "source": SOURCE, "license": "Apache-2.0",
            "sample_rate": clap.SR, "seconds": clap.MAX_SECONDS, "dim": clap.DIM,
            "templates": list(clap.TEMPLATES),
            "files": {name: {"sha256": sha256(work / name), "size": (work / name).stat().st_size}
                      for name in clap.MODEL_FILES},
        }
        (work / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        package = dist / clap.MODEL_ZIP
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in (*clap.MODEL_FILES, "manifest.json"):
                info = zipfile.ZipInfo(name, DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(work / name, "rb") as f, z.open(info, "w", force_zip64=True) as out:
                    shutil.copyfileobj(f, out, 1 << 20)
    print(f"{package}: {package.stat().st_size:,} bytes")
    print(f"sha256 (va en clap.MODEL_SHA256): {sha256(package)}")


if __name__ == "__main__":
    main()
