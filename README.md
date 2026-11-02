# Sample Scout

Librería de samples para Windows que **se analiza y ordena sola**, sin mover ni renombrar tus
archivos. Elegís las carpetas, la app indexa todo y detecta el tipo (loop o one-shot), el BPM,
la tonalidad y el instrumento. Desde la lista escuchás cada sample y lo arrastrás directo a
Ableton o a cualquier DAW.

[![Descargar instalador para Windows](https://img.shields.io/badge/Descargar-instalador%20para%20Windows-0f766e?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/LeandroDoliri/sample-scout/releases/latest/download/SampleScoutSetup.exe)

- [Instalación](#instalación)
- [Uso](#uso)
- [Cómo ordena la librería](#cómo-ordena-la-librería)
- [Actualizaciones](#actualizaciones)
- [Tus datos](#tus-datos)
- [Solución de problemas](#solución-de-problemas)
- [Desarrollo](#desarrollo)
- [Publicar una versión](#publicar-una-versión)
- [Próximos pasos](#próximos-pasos)

## Instalación

Descargá y ejecutá `SampleScoutSetup.exe`, con el botón de arriba o desde
[Releases](https://github.com/LeandroDoliri/sample-scout/releases/latest).

- Trae todo lo necesario (su propio Python con las librerías de audio): no hay que instalar nada más.
- No pide permisos de administrador. Se instala en `%LOCALAPPDATA%\Programs\Sample Scout`.
- Crea un acceso directo en el menú Inicio y, si querés, en el escritorio.
- Se desinstala desde "Agregar o quitar programas". Tu librería se conserva.

Requiere Windows 10 u 11 de 64 bits (x64 o ARM64; en ARM64 corre emulado).

## Uso

1. **Agregar carpeta…** (barra superior): elegí una carpeta de samples. Podés agregar varias.
   La app las indexa y analiza en segundo plano. La barra de abajo muestra el avance y la lista
   se puede usar mientras tanto. Lo que todavía no se analizó muestra `…`.
2. **Filtrá** con el panel izquierdo:
   - **Instrumento:** cada categoría con su cantidad. "Sin clasificar" junta lo que no se pudo
     identificar.
   - **Tipo:** loops o one-shots.
   - **BPM:** rango desde–hasta (`—` = sin límite).
   - **Key:** una tonalidad exacta.
   - **Buscar** (arriba): palabras sueltas sobre el nombre y las carpetas, por ejemplo
     `techno vol 2 bass`.
3. **Escuchá:** al seleccionar una fila se reproduce si está tildado "Escuchar al seleccionar".
   Con las flechas recorrés la lista escuchando, y `Espacio` reproduce o detiene.
4. **Arrastrá** una o varias filas (`Ctrl`/`Shift` para elegir varias) a Ableton, al Explorador
   o a cualquier programa que acepte archivos. Se arrastra el archivo original.
5. **Ordená** haciendo clic en el encabezado de cualquier columna.
6. **Clic derecho** sobre una o varias filas: favorito, estrellas, colecciones, editar datos y
   tags, mostrar en el Explorador o copiar la ruta.
7. **Portada y detalle:** el panel de la derecha muestra la portada del pack y los datos del
   sample elegido, y cada fila lleva una miniatura de la portada. La portada es la imagen
   (`.jpg`, `.jpeg`, `.png` o `.webp`) más cercana subiendo desde la carpeta del sample hasta
   la carpeta que agregaste, nunca más arriba. Si en una carpeta hay varias, gana la que se
   llama `cover…`, `artwork…`, `folder…`, `front…` o como el pack; si no, la más pesada. Se
   busca al escanear: si agregás una portada a un pack, aparece con **Re-escanear**.

### Organizar a mano

Además de lo automático, podés ordenar la librería a tu gusto. Todo funciona con una o varias
filas elegidas.

| Qué | Cómo |
|---|---|
| **Favorito** | `F`, clic en la ☆ de la primera columna o clic derecho. Si ya lo eran todos, los desmarca. |
| **Estrellas** (0 a 5) | Teclas `1`…`5` (`0` las borra), clic sobre la columna Estrellas o clic derecho. |
| **Colecciones** | **Nueva colección…** (panel izquierdo) o clic derecho → *Agregar a colección*. También podés arrastrar filas sobre una colección del panel. Un sample puede estar en varias. Clic derecho sobre una colección para renombrarla o borrarla; dentro de una colección, `Supr` saca los elegidos. |
| **Historial** | En el panel *Biblioteca*: los últimos 200 samples que escuchaste, del más reciente al más viejo. Clic derecho para vaciarlo. |
| **Editar datos y tags** | `F2` o clic derecho → *Editar datos y tags…*: tipo, instrumento, BPM y key, más tags libres para agregar o quitar. Con varias filas, cada campo muestra "(varios)" si no coinciden y solo se cambia lo que toques. Dejá el BPM vacío o elegí `—` para dejar un dato vacío. |

**Filtros:** *Biblioteca* (toda la librería, historial o una colección), *Estrellas* (mínimo),
*Tag* y *Solo favoritos* se suman a los demás filtros. La búsqueda de texto también encuentra
los tags.

Lo que corregís a mano queda con fuente `user`: gana sobre cualquier otra fuente y ni
re-escanear ni re-analizar lo pisa. Para volver a lo automático, clic derecho → *Restablecer
datos automáticos* (se recalcula con el próximo escaneo).

Favoritos, estrellas, tags, colecciones, historial y correcciones se guardan por ruta de
archivo: sobreviven a re-escanear y a quitar y volver a agregar la carpeta. Si movés o
renombrás un archivo en el disco, para la app es otro sample y esos datos no lo siguen.

Para saber de dónde salió un dato, pasá el mouse sobre la fila. El tooltip muestra la ruta, la
fuente de cada dato (`user`, `meta`, `name` o `audio`, explicadas abajo) y los tags.

**Re-escanear** vuelve a recorrer las carpetas: suma lo nuevo, re-analiza lo modificado y
quita lo borrado. También pasa solo cada vez que abrís la app. **Quitar carpeta** (elegila
primero en la lista "Carpetas") la saca de la librería sin tocar los archivos. Mientras haya un
análisis en curso no hace nada: esperá a que termine.

## Cómo ordena la librería

Cada dato se completa con la fuente más confiable disponible, en este orden:

| Fuente | De dónde sale | Qué aporta | Confiabilidad |
|---|---|---|---|
| `user` | Lo que corregiste a mano (*Editar datos y tags…*) | Tipo, BPM, key, instrumento | Manda siempre |
| `meta` | Chunk `acid` del WAV (lo escriben Ableton, Acid y muchos packs) | BPM, one-shot | Alta |
| `name` | Nombre del archivo y carpetas | BPM, key, instrumento, loop / one-shot | Alta en packs comerciales |
| `audio` | Análisis de la señal con librosa | Duración, tipo, BPM, key, instrumento de one-shots | Media |

**Desde el nombre** (`parser.py`), por ejemplo en `Techno Vol 2\Loops\TV2_124_Fm_Bass_Loop_03.wav`:
- **BPM:** `124bpm`, `124 bpm` o un número suelto entre 70 y 180. No cuenta si viene después
  de `vol`, `part`, etc.
- **Key:** `Fm`, `F#min`, `Ebmin`, `A minor`… Se normaliza con sostenidos (`Ebm` → `D#m`). Una
  letra sola (`C`) solo cuenta en mayúscula y pegada a un número, porque "A Kick" no está en La.
- **Instrumento:** un diccionario de sinónimos (`bd` = `kick`, `vox` = `vocal`, `hh` = `hat`…).
  Primero mira el nombre del archivo y después las carpetas, de la más profunda a la más alta.
  Los géneros que contienen instrumentos ("Drum and Bass", "Bass House") se ignoran.
- **Tipo:** `loop`, `one shot`, `hit`.

**Desde el audio** (`analyzer.py`), solo para lo que falte:
- **Tipo:** dura menos de 1,5 s, o hasta 6 s con pocos ataques fuertes → one-shot. Si no → loop.
- **BPM** (solo loops): el tempo detectado se lleva al rango 70–180 y se corrige con el largo
  del archivo. Si el loop dura un número entero de compases de 4/4, el BPM sale exacto de ahí.
  A los sonidos sostenidos (pads, drones) no se les inventa tempo.
- **Key:** perfil cromático comparado con los 24 perfiles de Krumhansl-Kessler. Si la
  coincidencia es baja, queda vacía. No se calcula para baterías.
- **Instrumento** (solo one-shots): una heurística espectral distingue kick, bajo, hi-hat y
  percusión. Los loops sin nombre útil quedan en "Sin clasificar" hasta que llegue el
  clasificador con IA (ver [Próximos pasos](#próximos-pasos)).

Para no confundir: un one-shot no toma el BPM de su nombre (ahí un número suele ser una
numeración, como `Kick 100.wav`), y a una batería no se le estima tonalidad.

## Actualizaciones

Al abrirse, la app consulta el último release de este repositorio. Si hay una versión nueva,
muestra un aviso arriba:

- **Actualizar:** baja solo los archivos de la app (unos KB), verifica el sha256 de cada uno,
  los reemplaza y se reinicia. Si algo falla, vuelve a dejar la versión anterior.
- **Descargar instalador:** aparece cuando la versión nueva cambia el Python que trae la app.
  Instalala encima: no se pierde nada.
- **Ver novedades:** abre la página del release. **Más tarde:** oculta el aviso hasta el
  próximo arranque.

Nunca se actualiza sin preguntar. Sin internet, no muestra nada.

## Tus datos

- Los samples **nunca se mueven, renombran ni modifican**: la app solo los lee.
- La librería (índice y análisis) está en `%APPDATA%\SampleScout\library.db`. Si la borrás, la
  app arranca de cero y re-analiza todo, y se pierden favoritos, estrellas, tags, colecciones,
  historial y correcciones, que viven en la misma base. Las bases de versiones anteriores se
  actualizan solas al abrir la app, sin perder nada.
- Con la app abierta sin consola, los errores se guardan en `%APPDATA%\SampleScout\app.log`.
- La única conexión a internet es la consulta de versiones a la API pública de GitHub.

## Solución de problemas

| Problema | Qué hacer |
|---|---|
| El Setup no arranca o se cierra sin mostrar nada | El **Control inteligente de aplicaciones** de Windows 11 bloquea instaladores sin firma digital. Instalá con el script (ver abajo). |
| La app no abre | Mirá `%APPDATA%\SampleScout\app.log`. |
| El análisis tarda | La primera vez analiza todo, y con miles de samples puede llevar un rato (en ARM64 más, por la emulación). Se puede usar la app mientras tanto, y si la cerrás sigue donde quedó. |
| Muchos samples en "Sin clasificar" | Es material sin nombre útil (loops propios, grabaciones). Buscalos por carpeta o por tipo. Mejora con el clasificador con IA. |
| Un BPM o una key están mal | Mirá la fuente en el tooltip. Si es `name`, el nombre del archivo lo dice así. Si es `audio`, es una estimación. |
| No suena | Revisá el dispositivo de salida predeterminado de Windows. La app usa ese. |

**Instalar sin el Setup** (PCs con Control inteligente de aplicaciones): cloná el repo e instalá
con el script, que deja lo mismo en la misma carpeta y se desinstala desde "Agregar o quitar
programas":

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1 -NoSetup
powershell -ExecutionPolicy Bypass -File tools\install_local.ps1
```

## Desarrollo

### Requisitos

- Windows, Python **x64** (3.12 o superior) y [uv](https://docs.astral.sh/uv/).
- En una PC **ARM64** también hace falta Python x64: `numba` y `soxr` (dependencias de
  librosa) no tienen paquetes para Windows ARM64.
- Para el instalador: [Inno Setup 6](https://jrsoftware.org/isinfo.php)
  (`winget install JRSoftware.InnoSetup`).

```bash
uv venv --python cpython-3.12-windows-x86_64-none .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python -m sample_scout     # la app
.venv/Scripts/python -m pytest           # tests
```

Corriendo desde el repo, la app usa la misma librería que la instalada
(`%APPDATA%\SampleScout`). Para usar otra: `SAMPLE_SCOUT_DB=ruta\otra.db`.

### Estructura

```
src/sample_scout/
  __init__.py     versión (lee VERSION) y APP_DIR (carpeta de la instalación o raíz del repo)
  __main__.py     python -m sample_scout
  app.py          ventana PySide6: filtros, tabla, preescucha, arrastre y aviso de actualización
  db.py           esquema SQLite, migraciones, consultas y datos del usuario (por ruta)
  scanner.py      escaneo incremental de carpetas y análisis en paralelo (ProcessPoolExecutor)
  parser.py       datos desde el nombre del archivo y las carpetas
  metadata.py     chunk acid de los WAV
  analyzer.py     análisis de audio con librosa
  updater.py      actualización desde los releases de GitHub
tests/            tests de parser.py, analyzer.py y de los datos del usuario (pytest)
tools/
  build_installer.ps1   arma el Python embebido, el instalador y el zip de actualización
  install_local.ps1     instala sin el Setup (PCs con Control inteligente de aplicaciones)
  release.ps1           publica la versión de VERSION en GitHub
  make_icon.py          genera icon.ico e icon.png (editá el script, no las imágenes)
  make_test_samples.py  librería sintética de resultado conocido para probar el análisis
  fake_release.py       imita la API de GitHub para probar la actualización sin publicar
installer/SampleScout.iss   script de Inno Setup
VERSION, RUNTIME, requirements.txt, CHANGELOG.md
```

### Probar

- **Lógica pura:** `pytest` cubre el parser de nombres, la estimación de BPM y tipo, la
  migración de la base, la precedencia de la fuente `user` y que los datos del usuario
  sobrevivan a re-escanear.
- **Análisis de audio:**
  `.venv/Scripts/python tools/make_test_samples.py C:\temp\ss-lib --analyze` genera samples
  sintéticos e imprime lo que detectó. El docstring del script tiene la tabla esperada.
  La base de prueba queda en esa carpeta, no en tu librería.
- **Actualización:** instalá la app, levantá `tools/fake_release.py 0.1.1` y abrí la app
  instalada con `SAMPLE_SCOUT_UPDATE_URL=http://127.0.0.1:8799` (los pasos están en el
  docstring del script). Con `fake_release.py 0.1.2 2` se prueba el caso que pide el
  instalador completo.
- **Interfaz sin ventana:** con `QT_QPA_PLATFORM=offscreen` se puede crear `MainWindow` desde
  un script y revisar `window.model.rows`, los filtros y `model.mimeData(...)`.

> La ruta de la carpeta temporal de algunas herramientas supera los 260 caracteres, y el Python
> x64 no la abre. Usá rutas cortas como `C:\temp\...` para las pruebas.

### Instalador

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1 [-Clean] [-NoSetup]
```

Genera en `dist\`:
- `SampleScoutSetup-<versión>.exe`: el instalador completo (~160 MB).
- `SampleScout-update-<versión>.zip`: el paquete que usa la actualización desde la app.

Cómo está armado: Python embebido oficial x64, con su `._pth` modificado para ver la carpeta
de la instalación, más las dependencias y el paquete `sample_scout\`. Los accesos directos
abren `python\pythonw.exe -m sample_scout`. No hay un `.exe` propio a propósito: Windows 11
bloquea los ejecutables sin firma, y `pythonw.exe` está firmado. Las descargas quedan en caché
en `build\downloads` (`-Clean` las borra).

## Publicar una versión

Versionado [semántico](https://semver.org/lang/es/): `MAJOR.MINOR.PATCH`.

1. Anotá los cambios en `CHANGELOG.md`, bajo un título `## [X.Y.Z] - AAAA-MM-DD`.
2. Subí el número en `VERSION`.
3. Si la versión nueva necesita otro Python (otra versión, o dependencias que no se pueden
   instalar con pip sobre el Python actual), subí también `RUNTIME`. Así las instalaciones
   viejas piden el instalador completo en lugar de actualizarse desde el zip.
4. Commiteá y pusheá a `main`.
5. Publicá:
   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\release.ps1
   ```
   Verifica que `main` esté limpio y al día, compila y crea el release `vX.Y.Z` con
   `SampleScoutSetup.exe` y el zip, usando como notas la entrada de `CHANGELOG.md`.

Las instalaciones existentes ven la versión nueva la próxima vez que abren la app.

## Próximos pasos

1. **Clasificación con IA** (PANNs o CLAP) para instrumentos de loops y material propio, en
   reemplazo de la heurística.
2. **"Sonidos parecidos"** con embeddings y búsqueda de vecinos más cercanos.
3. **Búsqueda por texto libre** con CLAP ("kick oscuro con punch").
4. Preescucha sincronizada al tempo del proyecto y filtro por tonalidad relativa.
5. Firma digital del instalador, para que el Control inteligente de aplicaciones no lo bloquee.
