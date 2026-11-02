# CLAUDE.md

Guía para Claude Code en este repositorio.

## Resumen

App de escritorio para Windows (PySide6) que indexa carpetas de samples en SQLite, los analiza
(tipo, BPM, key, instrumento) y permite filtrarlos, escucharlos y arrastrarlos a Ableton. Los
textos de la interfaz y los comentarios van en español rioplatense.

- `parser.py`: datos desde el nombre de archivo y las carpetas (sin I/O; tests en `tests/`).
- `metadata.py`: chunk `acid` de WAV.
- `analyzer.py`: librosa. Corre en procesos aparte (`scanner._analyze_job`, ProcessPoolExecutor).
- `scanner.py`: escaneo incremental (mtime + tamaño) y prioridad de fuentes `meta` > `name` > `audio`.
- `db.py`: esquema y consultas. Base en `%APPDATA%\SampleScout\library.db` (`SAMPLE_SCOUT_DB` la cambia).
- `app.py`: ventana. El arrastre sale de `SampleModel.mimeData` como lista de URLs de archivo.
- `updater.py`: actualización desde los releases de GitHub.

## Comandos

```bash
.venv/Scripts/python -m sample_scout   # app
.venv/Scripts/python -m pytest         # tests
```

La PC de desarrollo es **Windows ARM64**: numba y soxr no tienen paquetes ARM64, así que el venv
y la instalación usan Python **x64** (emulado). No crear el venv con el Python 3.14 ARM64 del sistema.

## Instalador y actualización (mismo esquema que music-downloader)

- `VERSION` (raíz) es la única fuente de la versión; `sample_scout/__init__.py` la lee
  (`APP_DIR` es la carpeta de la instalación o la raíz del repo).
- `tools/build_installer.ps1` arma `build\stage` con el Python embebido oficial x64
  (su `._pth` agrega `..` para ver `sample_scout\` y activa `import site`), instala
  `requirements.txt` con `--no-build-isolation`, genera `dist\SampleScout-update-X.Y.Z.zip`
  (archivos de la app + `manifest.json` con sha256 y `min_runtime`) y compila Inno Setup.
- Accesos directos: `python\pythonw.exe -m sample_scout`. No hay lanzador `.exe` propio porque
  el Control inteligente de aplicaciones bloquea ejecutables sin firma; `tools/install_local.ps1`
  instala sin el Setup en PCs con ese control activado.
- Los `.ps1` y el `.iss` llevan BOM UTF-8 (PowerShell 5.1 lee mal los acentos sin BOM).
- `updater.apply` solo reemplaza `APP_FILES` (`sample_scout`, `icon.ico`, `VERSION`,
  `requirements.txt`), verifica sha256 y manifest, corre pip si cambió `requirements.txt` y
  restaura la copia si algo falla. Si `min_runtime` > `RUNTIME` de la instalación, lanza
  `NeedsInstaller`. Desde un checkout git solo avisa. `SAMPLE_SCOUT_UPDATE_URL` apunta a otro
  servidor para probar.
- Publicar: subir `VERSION` (y `RUNTIME` si cambia el Python), commit + push a `main`,
  `tools/release.ps1`.
- `requirements.txt` usa `PySide6-Essentials` + `PySide6-Addons` (QtMultimedia), no `PySide6`,
  que suma QtWebEngine y ~85 MB al instalador.
