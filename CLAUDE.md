# CLAUDE.md

Guía para Claude Code en este repositorio. La documentación para usuarios y el detalle de
cómo se ordena la librería están en README.md; este archivo cubre lo que hace falta para
cambiar el código sin romper nada.

## Resumen

App de escritorio para Windows (PySide6) que indexa carpetas de samples en SQLite, los analiza
(tipo, BPM, key, instrumento) y permite filtrarlos, escucharlos y arrastrarlos a Ableton. Se
distribuye con un instalador (Inno Setup + Python embebido) y se actualiza desde GitHub Releases.

Idioma: interfaz, comentarios, docstrings y documentación en español rioplatense (voseo).
Nombres de código en inglés.

## Comandos

```bash
.venv/Scripts/python -m sample_scout                                   # app
.venv/Scripts/python -m pytest                                         # tests
.venv/Scripts/python tools/make_test_samples.py C:\temp\ss-lib --analyze   # análisis de punta a punta
.venv/Scripts/python tools/fake_release.py 0.1.1 [min_runtime]         # GitHub falso para el updater
powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1     # instalador + zip
powershell -ExecutionPolicy Bypass -File tools\release.ps1             # publicar VERSION
```

La PC de desarrollo es **Windows ARM64**: numba y soxr no tienen paquetes ARM64, así que el venv
y la instalación usan Python **x64** (emulado). No crear el venv con el Python 3.14 ARM64 del
sistema. Las rutas largas (>260 caracteres, como la carpeta temporal de la sesión) no las abre
el Python x64: usar `C:\temp\...` o `%TEMP%\ss-...` para pruebas.

## Arquitectura

- `parser.py` (sin I/O, testeado): datos desde la ruta. El nombre del archivo manda sobre las
  carpetas, y las carpetas profundas sobre las de arriba. Las tonalidades se normalizan a
  sostenidos. Para sumar sinónimos, editar `INSTRUMENTS` (y `INSTRUMENT_LABELS` si es una
  categoría nueva; `DRUM_INSTRUMENTS` si no tiene tonalidad).
- `metadata.py`: chunk `acid` de WAV; el tempo solo vale si hay beats > 0 y no es one-shot.
- `analyzer.py`: librosa, importado adentro de las funciones (para que la ventana arranque
  rápido). `STRONG_ONSET` es un umbral absoluto sobre la envolvente de onsets (escala log,
  independiente del volumen) que separa golpes de un sonido sostenido. `estimate_bpm` pliega
  el tempo a 70–180 y prefiere el BPM que sale de un número entero de compases.
- `scanner.py`: `scan_root` indexa (mtime + tamaño para saber qué cambió) y guarda lo que
  sale de `meta`/`name`. `analyze_pending` corre `_analyze_job` en un ProcessPoolExecutor y
  `_apply` completa solo los campos vacíos con fuente `audio`. Reglas: one-shot → se descarta
  el BPM que venga de `name`; batería → se descarta la key de `audio`. Cada campo guarda su
  fuente en `<campo>_source`.
- `db.py`: una conexión por hilo, WAL. `SAMPLE_SCOUT_DB` cambia la base. `migrate` lleva
  cualquier base vieja al `SCHEMA_VERSION` actual (`PRAGMA user_version`) sin perder datos.
  Los datos del usuario (`marks`, `user_fields`, `tags`, `collections`, `collection_items`,
  `history`) van en tablas aparte con clave por **ruta**, no por `samples.id`: `samples` se
  borra y se regenera al quitar carpetas o re-indexar, y estos datos tienen que sobrevivir.
- Fuente `user`: `set_user_field` escribe `user_fields` y la fila de `samples`; `_index_file`
  vuelve a aplicar `user_fields` después de cada upsert y `_apply` saltea los campos `user`
  (relee la fila actual, porque el usuario pudo editar durante el análisis). Un valor `user`
  en NULL significa "vacío a propósito": no se re-estima.
- Portadas: `scanner.CoverFinder` (cache por carpeta) guarda en `samples.cover` solo la ruta;
  `scan_root` la actualiza también para archivos sin cambios. En `app.py`, `CoverCache` lee y
  escala con `QImageReader` en un `QThreadPool` (QImage en el hilo, QPixmap solo en la
  ventana). Columnas nuevas de `samples` van en `db.ADDED_COLUMNS` (ALTER TABLE al migrar;
  sus índices, en `db.ADDED_INDEXES`).
- Onda y duplicados: `samples.peaks` (`analyzer.WAVE_POINTS` bytes) y `samples.content_hash`
  (en WAV/AIFF solo formato + muestras, para que la metadata no cuente) se calculan en
  `_analyze_job` y `_index_file` los pone en NULL cuando cambia mtime/tamaño. `analyze_pending`
  también toma las filas analizadas con `peaks` NULL (bases viejas) y solo les calcula eso.
  Si falla, `peaks` queda en `b""` para no reintentar. La ventana pide la onda en un
  `QThreadPool` si el análisis todavía no llegó (`db.set_peaks` no pisa una existente).
- `app.py`: `LibraryWorker` (escaneo + análisis) y `TaskWorker` (tareas cortas, como chequear o
  aplicar la actualización) corren en QThreads; nunca tocar widgets desde ellos, solo emitir
  señales. El arrastre sale de `SampleModel.mimeData` (URLs de archivo: Ableton las recibe como
  desde el Explorador). Con pythonw los errores van a `%APPDATA%\SampleScout\app.log`.
- `clap.py` (funciones de IA, opcionales): modelo `clap-general-v1` (LAION `clap-htsat-unfused`
  en ONNX: audio fp32, texto int8) que se baja a demanda de un release propio
  (`models-clap-general-v1`, **prerelease**, nunca "Latest") a `%LOCALAPPDATA%\SampleScout\models`
  (`SAMPLE_SCOUT_MODELS` / `SAMPLE_SCOUT_MODEL_URL` para pruebas). El zip se verifica contra
  `MODEL_SHA256` (en el código) y cada archivo contra su manifest. onnxruntime y tokenizers se
  importan adentro de las funciones; nada de torch ni transformers en la app. El mel está portado
  de `ClapFeatureExtractor` y `tests/test_clap.py` lo compara con `fixtures/clap_reference.npz`.
  `scanner.embed_pending` corre después de `analyze_pending` en **un** proceso
  (`ProcessPoolExecutor(max_workers=1)`, lotes de `clap.BATCH`, núcleos − 2 hilos) y guarda en
  `embeddings` (por ruta + modelo, float16, válido mientras coincidan mtime y tamaño; `b""` =
  audio ilegible). La ventana carga los vectores en `clap.Index` (float32, fuerza bruta) y el
  encoder de texto recién al buscar por sonido. Un modelo nuevo = otro `MODEL_ID` y otro tag.
- `run_task(fn, on_done, on_failed)`: on_done/on_failed tienen que ser **métodos** de la ventana
  (así Qt los corre en su hilo); una función anidada correría en el hilo del worker.
- Multiprocessing en Windows usa spawn: todo lo que se manda a los procesos tiene que ser
  picklable y estar a nivel de módulo (`_analyze_job`).

## Instalador y actualización (mismo esquema que music-downloader)

- El modelo de IA no va en el instalador ni en `APP_FILES`; se publica aparte (README, "Publicar
  el modelo de IA") con `tools/build_clap_model.py`.
- `VERSION` (raíz) es la única fuente de la versión: la leen `sample_scout/__init__.py`
  (`APP_DIR` = carpeta de la instalación o raíz del repo), `pyproject.toml` (dinámica) y
  `build_installer.ps1`.
- `tools/build_installer.ps1` arma `build\stage` con el Python embebido oficial x64 (su `._pth`
  agrega `..` para ver `sample_scout\` y activa `import site`), instala `requirements.txt` con
  `--no-build-isolation`, genera `dist\SampleScout-update-X.Y.Z.zip` (archivos de la app +
  `manifest.json` con sha256 y `min_runtime`) y compila Inno Setup.
- Accesos directos: `python\pythonw.exe -m sample_scout`. No hay lanzador `.exe` propio porque
  el Control inteligente de aplicaciones bloquea ejecutables sin firma. `tools/install_local.ps1`
  instala sin el Setup en PCs con ese control activado.
- Los `.ps1` y el `.iss` llevan BOM UTF-8 (PowerShell 5.1 lee mal los acentos sin BOM). En
  PowerShell 5.1 con `$ErrorActionPreference = 'Stop'`, un comando nativo que escribe en stderr
  corta el script: no redirigir stderr de comandos que pueden fallar a propósito.
- `updater.apply` solo reemplaza `APP_FILES` (`sample_scout`, `icon.ico`, `VERSION`,
  `requirements.txt`), verifica el digest de GitHub, el manifest y cada sha256, corre pip si
  cambió `requirements.txt` y restaura la copia si algo falla. Si `min_runtime` > `RUNTIME` de
  la instalación, lanza `NeedsInstaller` sin tocar nada. Desde un checkout git solo avisa.
- Si se agrega un archivo nuevo a la app fuera de `sample_scout/`, sumarlo a `APP_FILES`, al
  zip de `build_installer.ps1` y a `fake_release.py`.
- `requirements.txt` usa `PySide6-Essentials` + `PySide6-Addons` (QtMultimedia), no `PySide6`,
  que suma QtWebEngine y ~85 MB al instalador. Mantenerlo alineado con `pyproject.toml`.

## Publicar

1. Entrada `## [X.Y.Z] - fecha` en `CHANGELOG.md` (pasar lo de `[Sin publicar]`).
2. Subir `VERSION`, y `RUNTIME` si cambia el Python o hay dependencias que pip no puede
   instalar sobre la instalación existente.
3. Commit + push a `main` y `tools/release.ps1` (toma las notas del CHANGELOG).

Al cambiar comportamiento visible, actualizar README.md (uso / cómo ordena) y `[Sin publicar]`
en CHANGELOG.md en el mismo commit.
