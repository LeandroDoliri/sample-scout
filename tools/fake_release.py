"""Servidor local que imita la API de releases de GitHub, para probar la actualización sin publicar.

Arma en memoria un paquete de actualización con los archivos actuales de src/ y la versión que
le pases, y responde `/releases/latest` y la descarga del zip igual que GitHub (incluido el
`digest` sha256 del asset).

Uso (desde la raíz del repo):
    .venv/Scripts/python tools/fake_release.py 0.1.1 [min_runtime]

Y en otra terminal, la app instalada apuntando a este servidor:
    $env:SAMPLE_SCOUT_UPDATE_URL = 'http://127.0.0.1:8799'
    & "$env:LOCALAPPDATA\\Programs\\Sample Scout\\python\\pythonw.exe" -m sample_scout

La app muestra el aviso de versión nueva; al tocar Actualizar debería reiniciarse con esa
versión. Con min_runtime mayor que el RUNTIME instalado (p. ej. 2), en cambio, debe pedir el
instalador completo sin tocar nada. Desde el repo (checkout git) solo muestra el aviso.
"""

import hashlib
import http.server
import io
import json
import sys
import zipfile
from pathlib import Path

PORT = 8799
ROOT = Path(__file__).resolve().parent.parent


def build_package(version: str, min_runtime: int) -> bytes:
    files = {
        "VERSION": (version + "\n").encode(),
        "requirements.txt": (ROOT / "requirements.txt").read_bytes(),
        "icon.ico": (ROOT / "icon.ico").read_bytes(),
    }
    for path in (ROOT / "src" / "sample_scout").glob("*.py"):
        files[f"sample_scout/{path.name}"] = path.read_bytes()
    manifest = {"version": version, "min_runtime": min_runtime,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr("manifest.json", json.dumps(manifest))
    return buffer.getvalue()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    version = sys.argv[1]
    min_runtime = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    package = build_package(version, min_runtime)
    asset = f"SampleScout-update-{version}.zip"
    release = {
        "tag_name": f"v{version}",
        "body": "Release de prueba (tools/fake_release.py)",
        "html_url": f"http://127.0.0.1:{PORT}/page",
        "assets": [{
            "name": asset,
            "browser_download_url": f"http://127.0.0.1:{PORT}/{asset}",
            "digest": "sha256:" + hashlib.sha256(package).hexdigest(),
        }],
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(release).encode() if self.path.endswith("/releases/latest") else package
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            print(f"  {self.path}")

    print(f"Release falso v{version} (min_runtime {min_runtime}) en http://127.0.0.1:{PORT}")
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
