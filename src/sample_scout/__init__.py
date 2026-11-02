"""Sample Scout: librería de samples que se analiza y ordena sola."""

from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
# Instalada: <instalación>\sample_scout, con VERSION al lado. En el repo: src\sample_scout,
# con VERSION en la raíz.
APP_DIR = PKG_DIR.parent if (PKG_DIR.parent / "VERSION").exists() else PKG_DIR.parent.parent


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return default


# El archivo VERSION es la única fuente de la versión (lo usa también tools/build_installer.ps1)
__version__ = _read_text(APP_DIR / "VERSION", "0.0.0")
