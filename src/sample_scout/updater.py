"""Actualización desde los releases de GitHub (el mismo esquema que Music Downloader).

Cada release trae `SampleScoutSetup.exe` (instalación completa) y
`SampleScout-update-X.Y.Z.zip`: solo los archivos de la app más un manifest.json con la versión,
el sha256 de cada archivo y `min_runtime`. La app baja el zip, lo verifica, reemplaza sus archivos
y se reinicia. Si la versión nueva necesita otro Python (min_runtime mayor que el RUNTIME de la
instalación), no toca nada y pide el instalador completo.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from sample_scout import APP_DIR, __version__, _read_text

try:
    APP_RUNTIME = int(_read_text(APP_DIR / "RUNTIME", "1"))
except ValueError:
    APP_RUNTIME = 1
# API de releases de GitHub. La variable de entorno permite probar contra un servidor local.
UPDATE_API = os.environ.get("SAMPLE_SCOUT_UPDATE_URL",
                            "https://api.github.com/repos/LeandroDoliri/sample-scout").rstrip("/")
UPDATE_ASSET = re.compile(r"^SampleScout-update-[\d.]+\.zip$")
# Lo que reemplaza una actualización; el resto de la carpeta (python\) es del instalador
APP_FILES = ("sample_scout", "icon.ico", "VERSION", "requirements.txt")
REQUIRED = ("sample_scout/__init__.py", "sample_scout/app.py", "VERSION", "requirements.txt")
UPDATE_WORK = APP_DIR / "_update"


class UpdateError(Exception):
    """La actualización no se aplicó. El mensaje está pensado para mostrárselo al usuario."""


class NeedsInstaller(UpdateError):
    """La versión nueva no se puede aplicar desde el zip: hay que bajar el instalador."""


def version_tuple(v: str) -> tuple[int, ...]:
    """"0.10.1" -> (0, 10, 1), para comparar versiones como números y no como texto."""
    return tuple(int(p) for p in re.findall(r"\d+", v))


def is_git_checkout() -> bool:
    """True si corre desde el repo: ahí solo se avisa, los archivos los maneja git."""
    return (APP_DIR / ".git").exists()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _http_get(url: str, timeout: float):
    # GitHub rechaza pedidos sin User-Agent
    headers = {"User-Agent": f"SampleScout/{__version__}", "Accept": "application/vnd.github+json"}
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)


def latest_release() -> dict | None:
    """El último release publicado, o None si no hay red o la respuesta no sirve."""
    try:
        with _http_get(f"{UPDATE_API}/releases/latest", timeout=6) as r:
            release = json.load(r)
        version = release["tag_name"].lstrip("vV")
        if not re.fullmatch(r"\d+(\.\d+)*", version):
            return None
        asset = next((a for a in release.get("assets") or []
                      if UPDATE_ASSET.match(a.get("name", ""))), None)
        return {"version": version, "notes": release.get("body") or "",
                "page": release.get("html_url") or "", "asset": asset}
    except Exception:
        return None


def check() -> dict:
    """Compara VERSION con el último release. Sin red o con error devuelve available=False.
    reason: '' (se puede actualizar desde la app), 'git' (checkout del repo: solo avisar) o
    'installer' (el release no trae el paquete .zip: hay que bajar el instalador)."""
    result = {"current": __version__, "latest": None, "available": False, "notes": "",
              "page": "", "can_apply": False, "reason": ""}
    release = latest_release()
    if not release:
        return result
    result.update(latest=release["version"], notes=release["notes"], page=release["page"],
                  available=version_tuple(release["version"]) > version_tuple(__version__))
    if is_git_checkout():
        result["reason"] = "git"
    elif not release["asset"]:
        result["reason"] = "installer"
    else:
        result["can_apply"] = True
    return result


def _verify(folder: Path, expected_version: str) -> dict:
    """Compara el paquete extraído con su manifest.json. Devuelve el manifest o lanza UpdateError."""
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise UpdateError("el paquete no trae un manifest.json válido")
    files = manifest.get("files") or {}
    if manifest.get("version") != expected_version:
        raise UpdateError(f"el paquete dice ser la versión {manifest.get('version')}, "
                          f"no la {expected_version}")
    for required in REQUIRED:
        if required not in files:
            raise UpdateError(f"al paquete le falta {required}")
    # Solo archivos de la app: un paquete no puede tocar python\
    if any(rel.split("/")[0] not in APP_FILES for rel in files):
        raise UpdateError("el paquete trae archivos fuera de la app")
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    present.discard("manifest.json")
    if present != set(files):
        raise UpdateError("los archivos del paquete no coinciden con el manifest")
    for rel, digest in files.items():
        if _sha256(folder / rel) != str(digest).lower():
            raise UpdateError(f"{rel} está dañado (el sha256 no coincide)")
    return manifest


def _swap_app_files(new: Path, app_dir: Path, backup: Path) -> None:
    """Pone los archivos de `new` en app_dir y guarda los anteriores en `backup`.
    Si algo falla a mitad de camino, vuelve a dejar los anteriores y relanza el error."""
    backup.mkdir(parents=True)
    moved, placed = [], []
    try:
        for name in APP_FILES:
            src, dst = new / name, app_dir / name
            # Lo que el paquete no trae se deja como está: la copia de seguridad se borra al
            # terminar, así que moverlo sería perderlo (p. ej. icon.ico, que usan los accesos directos)
            if not src.exists():
                continue
            if dst.exists():
                os.replace(dst, backup / name)
                moved.append(name)
            os.replace(src, dst)
            placed.append(name)
    except Exception:
        for name in placed:
            dst = app_dir / name
            shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
        for name in moved:
            os.replace(backup / name, app_dir / name)
        raise


def _python(windowless: bool) -> str:
    """python.exe / pythonw.exe de la instalación (firmados por la PSF; nunca un .exe propio)."""
    folder = Path(sys.executable).parent
    exe = folder / ("pythonw.exe" if windowless else "python.exe")
    return str(exe if exe.exists() else sys.executable)


def apply(log: Callable[[str], None]) -> str:
    """Baja el paquete del último release y reemplaza los archivos de la app.
    Devuelve la versión instalada; lanza UpdateError (o NeedsInstaller) si no se pudo."""
    if is_git_checkout():
        raise UpdateError("estás usando el código del repositorio: actualizá con git pull")
    release = latest_release()
    if not release:
        raise UpdateError("no se pudo consultar GitHub; revisá tu conexión a internet")
    if version_tuple(release["version"]) <= version_tuple(__version__):
        raise UpdateError("ya tenés la última versión")
    asset = release["asset"]
    if not asset:
        raise NeedsInstaller(release["page"])

    pip_ran = False  # pip no se puede deshacer: si corrió, el error no promete que nada cambió
    shutil.rmtree(UPDATE_WORK, ignore_errors=True)
    UPDATE_WORK.mkdir()
    try:
        package = UPDATE_WORK / "update.zip"
        log(f"Descargando Sample Scout {release['version']}…")
        with _http_get(asset["browser_download_url"], timeout=30) as r, open(package, "wb") as f:
            shutil.copyfileobj(r, f)
        # GitHub publica el sha256 de cada asset ("sha256:<hex>")
        digest = asset.get("digest") or ""
        if digest.startswith("sha256:") and _sha256(package) != digest[7:].lower():
            raise UpdateError("la descarga llegó dañada (el sha256 no coincide con el de GitHub)")

        new = UPDATE_WORK / "new"
        with zipfile.ZipFile(package) as z:
            for name in z.namelist():
                parts = name.replace("\\", "/").split("/")
                if name.startswith(("/", "\\")) or ":" in name or ".." in parts:
                    raise UpdateError(f"el paquete trae una ruta no permitida: {name}")
            z.extractall(new)
        manifest = _verify(new, release["version"])
        log("Paquete verificado: todos los archivos coinciden con su sha256.")

        if int(manifest.get("min_runtime") or 1) > APP_RUNTIME:
            raise NeedsInstaller(release["page"])

        new_reqs = new / "requirements.txt"
        if _read_text(APP_DIR / "requirements.txt", None) != _read_text(new_reqs):
            log("Instalando las dependencias de la versión nueva…")
            pip_ran = True
            done = subprocess.run(
                [_python(windowless=False), "-m", "pip", "install", "--quiet",
                 "--disable-pip-version-check", "--no-warn-script-location",
                 "--no-build-isolation", "-r", str(new_reqs)],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if done.returncode != 0:
                raise UpdateError("pip no pudo instalar las dependencias nuevas")

        try:
            _swap_app_files(new, APP_DIR, UPDATE_WORK / "backup")
        except PermissionError as e:
            raise UpdateError(f"un archivo de la app está en uso ({e.filename}); "
                              "cerrá otras ventanas de Sample Scout y volvé a intentar")
        return release["version"]
    except UpdateError as e:
        if pip_ran and not isinstance(e, NeedsInstaller):
            raise UpdateError(f"{e}. Los archivos de la app quedaron como estaban, pero algunas "
                              "dependencias pueden haber quedado actualizadas") from e
        raise
    except Exception as e:
        raise UpdateError(str(e)) from e
    finally:
        shutil.rmtree(UPDATE_WORK, ignore_errors=True)


def restart() -> None:
    """Abre la versión nueva en otro proceso (quien llama cierra la ventana actual)."""
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([_python(windowless=True), "-m", "sample_scout"], cwd=str(APP_DIR),
                     creationflags=flags, close_fds=True)
