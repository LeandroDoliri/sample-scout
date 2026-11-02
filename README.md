# Sample Scout

Librería de samples para Windows que **se analiza y ordena sola**, sin mover ni renombrar tus
archivos. Elegís las carpetas, la app indexa todo y detecta el tipo (loop o one-shot), el BPM,
la tonalidad y el instrumento. Desde la lista escuchás cada sample y lo arrastrás directo a
Ableton o a cualquier DAW.

[![Descargar instalador para Windows](https://img.shields.io/badge/Descargar-instalador%20para%20Windows-0f766e?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/LeandroDoliri/sample-scout/releases/latest/download/SampleScoutSetup.exe)

- [Instalación](#instalación)
- [Uso](#uso)
- [Funciones de IA](#funciones-de-ia)
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
   - **Duración:** rango en segundos, igual que el BPM. Lo que todavía no se analizó no tiene
     duración y no aparece mientras el filtro esté puesto.
   - **Key:** una tonalidad exacta.
   - **Buscar** (arriba): palabras sueltas sobre el nombre y las carpetas, por ejemplo
     `techno vol 2 bass`. Con las [funciones de IA](#funciones-de-ia) activadas, el selector
     de al lado pasa a **Por sonido** para buscar por descripción.
3. **Escuchá:** al seleccionar una fila se reproduce si está tildado "Escuchar al seleccionar".
   Con las flechas recorrés la lista escuchando, y `Espacio` reproduce o detiene.
4. **Arrastrá** una o varias filas (`Ctrl`/`Shift` para elegir varias) a Ableton, al Explorador
   o a cualquier programa que acepte archivos. Se arrastra el archivo original.
5. **Ordená** haciendo clic en el encabezado de cualquier columna. **Clic derecho** en el
   encabezado para elegir qué columnas ver (siempre queda al menos una) o *Restablecer
   columnas*; arrastrá un encabezado para cambiar el orden. Las columnas visibles, su orden y
   su ancho se recuerdan entre aperturas (en `settings.ini`, al lado de la base).
6. **Clic derecho** sobre una o varias filas: favorito, estrellas, colecciones, editar datos y
   tags, mostrar en el Explorador o copiar la ruta.
7. **Portada y detalle:** el panel de la derecha muestra la portada del pack y los datos del
   sample elegido, y cada fila lleva una miniatura de la portada. La portada es la imagen
   (`.jpg`, `.jpeg`, `.png` o `.webp`) más cercana subiendo desde la carpeta del sample hasta
   la carpeta que agregaste, nunca más arriba. Si en una carpeta hay varias, gana la que se
   llama `cover…`, `artwork…`, `folder…`, `front…` o como el pack; si no, la más pesada. Se
   busca al escanear: si agregás una portada a un pack, aparece con **Re-escanear**.
8. **Forma de onda:** debajo de la portada se ve la onda del sample elegido, con el cursor de
   reproducción avanzando. Hacé clic sobre la onda para reproducir desde ese punto. Se calcula
   una vez (en el análisis, o en segundo plano al elegir un sample que todavía no la tiene) y
   queda guardada en la base; se recalcula solo si el archivo cambia. También hay una mini onda
   por fila: clic derecho en el encabezado → *Forma de onda (mini)* (arranca oculta).
9. **Duplicados:** en el panel *Biblioteca*, la vista **Duplicados** junta los archivos con el
   mismo audio aunque estén en otras carpetas o con otro nombre. Cada grupo va junto y con un
   fondo que alterna. En el panel de la derecha, un sample duplicado lista sus otras copias:
   clic en una para ir a ella (también con clic derecho → *Ir a otra copia*). *Mostrar en el
   Explorador* abre la carpeta de cada una. El filtro **Ocultar duplicados** deja uno por grupo
   en cualquier vista. La app **no borra ni mueve** archivos: si querés limpiar, hacelo desde
   el Explorador.

   Para comparar se usa una huella del audio: en WAV y AIFF solo cuentan el formato y las
   muestras, así que dos copias con distinta metadata (por ejemplo, una a la que Ableton le
   guardó el tempo) cuentan como duplicadas. En MP3, FLAC y OGG se compara el archivo entero.
   La huella se calcula en el análisis y solo se recalcula si el archivo cambia (fecha o
   tamaño). Al actualizar desde una versión anterior, la app calcula ondas y huellas de toda la
   librería una vez, en segundo plano.
10. **Sonidos parecidos y búsqueda por sonido:** ver [Funciones de IA](#funciones-de-ia).

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

**Filtros:** *Biblioteca* (toda la librería, historial, duplicados o una colección),
*Estrellas* (mínimo), *Tag*, *Solo favoritos* y *Ocultar duplicados* se suman a los demás
filtros. La búsqueda de texto también encuentra
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

## Funciones de IA

Opcionales y **locales**: la app escucha tus samples con un modelo de IA que corre en tu PC
(CLAP de LAION, licencia Apache-2.0). No se manda nada a ningún servidor.

**Activarlas:** botón **IA** (barra superior) → *Activar funciones de IA…*. La app baja el
modelo una sola vez (**unos 195 MB**, con barra de avance, se puede cancelar y reintenta sola
si se corta), verifica el sha256 de todo y lo guarda en
`%LOCALAPPDATA%\SampleScout\models\clap-general-v1\`. Sin el modelo, o sin conexión al
activarlas, la app anda igual que siempre y estas funciones quedan apagadas.

Después, en segundo plano y después del análisis, la app **escucha** cada sample (los
primeros 10 segundos) y guarda una "huella de sonido" en la base. Lleva unos 0,15 s por sample
(unos 25 minutos cada 10.000) y la barra de abajo muestra el avance (`IA: escuchando samples
…`). Solo se hace una vez: se repite para un archivo si cambia. Mientras tanto, lo que ya se
escuchó se puede usar.

- **Sonidos parecidos:** clic derecho sobre un sample → *≈ Sonidos parecidos* (o `Ctrl+P`, o el
  enlace del panel de la derecha). Aparece la vista **≈ Parecidos a …** en el panel
  *Biblioteca* con los 100 más parecidos, del más al menos parecido. Los filtros (tipo, BPM,
  instrumento, búsqueda por nombre…) siguen funcionando sobre esa vista: por ejemplo, los
  one-shots más parecidos a un loop. El tooltip y el panel de detalle muestran el porcentaje
  de parecido.
- **Búsqueda por sonido:** elegí **Por sonido (IA)** al lado del buscador y describí lo que
  buscás: `kick oscuro con punch`, `redoblante crujiente`, `acordes de piano jazzeros`. La
  lista muestra los 100 que mejor coinciden, y los demás filtros también valen. El modelo
  entiende inglés: la app traduce sola los términos de producción más comunes
  (redoblante → snare, bajo → bass, cálido → warm, subida → riser…), y los anglicismos
  (kick, hi-hat, pad, lead) andan directo. Si algo no da lo que esperás, probá en inglés. La
  primera búsqueda tarda un par de segundos más (carga el modelo de texto).

**Desactivarlas:** botón **IA** → destildá *Funciones de IA activadas*. Deja de escuchar
samples y se ocultan las opciones; el modelo queda en el disco para volver a activarlas.
**Borrar el modelo:** botón **IA** → *Borrar el modelo…* borra la carpeta del modelo y las
huellas de sonido guardadas (tus samples y tus datos no se tocan). Se puede volver a activar
cuando quieras.

Recursos: escuchando, el proceso de fondo usa ~1 GB de RAM y todos los núcleos menos dos (la
ventana sigue fluida), y lo libera al terminar. Cada huella ocupa 1 KB en la base (10 MB cada
10.000 samples).

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
- La disposición de las columnas y si las funciones de IA están activadas están en
  `%APPDATA%\SampleScout\settings.ini`. Borrarlo equivale a *Restablecer columnas*.
- El modelo de IA, si lo activaste, está en `%LOCALAPPDATA%\SampleScout\models\` (unos
  250 MB descomprimido). Se puede borrar desde la app o a mano con la app cerrada. Las
  actualizaciones de la app no lo tocan.
- Las únicas conexiones a internet son la consulta de versiones a la API pública de GitHub y,
  solo si activás las funciones de IA, la descarga del modelo desde los releases de este
  repositorio.

## Solución de problemas

| Problema | Qué hacer |
|---|---|
| El Setup no arranca o se cierra sin mostrar nada | El **Control inteligente de aplicaciones** de Windows 11 bloquea instaladores sin firma digital. Instalá con el script (ver abajo). |
| La app no abre | Mirá `%APPDATA%\SampleScout\app.log`. |
| El análisis tarda | La primera vez analiza todo, y con miles de samples puede llevar un rato (en ARM64 más, por la emulación). Se puede usar la app mientras tanto, y si la cerrás sigue donde quedó. |
| Muchos samples en "Sin clasificar" | Es material sin nombre útil (loops propios, grabaciones). Buscalos por carpeta o por tipo. Mejora con el clasificador con IA. |
| No se puede activar la IA | Hace falta internet una vez para bajar el modelo. Si la descarga llega dañada, la app no lo instala: tocá *Reintentar*. |
| "Sonidos parecidos" dice que todavía no escuchó el sample | Está calculando las huellas de sonido (barra de abajo). Esperá a que llegue a ese sample. |
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
  scanner.py      escaneo incremental de carpetas, análisis en paralelo (ProcessPoolExecutor)
                  y embeddings de CLAP (un solo proceso aparte)
  clap.py         funciones de IA: descarga del modelo, mel, encoders ONNX, traducción y búsqueda
  parser.py       datos desde el nombre del archivo y las carpetas
  metadata.py     chunk acid de los WAV
  analyzer.py     análisis de audio con librosa
  updater.py      actualización desde los releases de GitHub
tests/            tests de parser.py, analyzer.py, datos del usuario, duplicados, onda, CLAP
                  (fixtures/clap_reference.npz: referencia de transformers) y updater
tools/
  build_installer.ps1   arma el Python embebido, el instalador y el zip de actualización
  install_local.ps1     instala sin el Setup (PCs con Control inteligente de aplicaciones)
  release.ps1           publica la versión de VERSION en GitHub
  make_icon.py          genera icon.ico e icon.png (editá el script, no las imágenes)
  make_test_samples.py  librería sintética de resultado conocido para probar el análisis
  fake_release.py       imita la API de GitHub para probar la actualización sin publicar;
                        con --model sirve el zip del modelo de IA
  build_clap_model.py   arma dist\clap-general-v1.zip (modelo, prompts, licencia, manifest)
  make_clap_fixture.py  genera el fixture de referencia de los tests de CLAP (con transformers)
installer/SampleScout.iss   script de Inno Setup
VERSION, RUNTIME, requirements.txt, CHANGELOG.md
```

### Probar

- **Lógica pura:** `pytest` cubre el parser de nombres, la estimación de BPM y tipo, la
  migración de la base, la precedencia de la fuente `user`, que los datos del usuario
  sobrevivan a re-escanear, la huella de duplicados y que la onda se invalide si cambia el
  archivo.
- **Análisis de audio:**
  `.venv/Scripts/python tools/make_test_samples.py C:\temp\ss-lib --analyze` genera samples
  sintéticos (con dos grupos de duplicados) e imprime lo que detectó. El docstring del
  script tiene la tabla esperada.
  La base de prueba queda en esa carpeta, no en tu librería.
- **Actualización:** instalá la app, levantá `tools/fake_release.py 0.1.1` y abrí la app
  instalada con `SAMPLE_SCOUT_UPDATE_URL=http://127.0.0.1:8799` (los pasos están en el
  docstring del script). Con `fake_release.py 0.1.2 2` se prueba el caso que pide el
  instalador completo.
- **Funciones de IA:** los tests de `test_clap.py` y `test_embeddings.py` que usan el modelo
  se saltean si no está instalado; con `SAMPLE_SCOUT_TEST_MODEL=<carpeta del modelo>` corren
  contra esa carpeta (comparan con la referencia de transformers: coseno ≥ 0,999 en audio).
  Para probar la descarga sin publicar nada:
  `.venv/Scripts/python tools/fake_release.py --model` y abrí la app con
  `SAMPLE_SCOUT_MODEL_URL=http://127.0.0.1:8799/clap-general-v1.zip` (y
  `SAMPLE_SCOUT_MODELS=C:\temp\ss-models` para no tocar el modelo real).
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

### Publicar el modelo de IA

El modelo va en un release aparte, con tag `models-clap-general-v1`, **marcado como
prerelease**: la app busca actualizaciones en `/releases/latest`, y un release de modelos no
puede quedar como "Latest" (igual, `updater.py` ignora los prerelease y los tags que no son
`vX.Y.Z`).

1. Armá el zip (necesita la exportación a ONNX del spike de CLAP y el texto de la licencia
   Apache-2.0); imprime el sha256:
   ```powershell
   .venv\Scripts\python tools\build_clap_model.py C:\temp\ss-clap\onnx\general apache-2.0.txt
   ```
2. Ese sha256 tiene que ser el de `clap.MODEL_SHA256` (el zip es reproducible: con las mismas
   entradas da el mismo).
3. Publicá:
   ```powershell
   gh release create models-clap-general-v1 dist\clap-general-v1.zip --prerelease --latest=false `
     --title "Modelo de IA: CLAP general v1" --notes "Modelo para las funciones de IA (no es una versión de la app)."
   ```
Un modelo nuevo es otro id (`clap-general-v2`), otra carpeta y otro tag: el viejo sigue
andando hasta que se actualice la app.

## Próximos pasos

1. **Clasificación del instrumento con IA** (CLAP, ya instalado para las funciones de IA)
   para loops y material propio, en reemplazo de la heurística.
2. Preescucha sincronizada al tempo del proyecto y filtro por tonalidad relativa.
3. Firma digital del instalador, para que el Control inteligente de aplicaciones no lo bloquee.
