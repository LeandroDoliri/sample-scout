# Sample Scout

Librería de samples para Windows que **se analiza y ordena sola**, sin mover ni renombrar tus
archivos. Elegís las carpetas, la app indexa todo, detecta tipo, BPM, tonalidad e instrumento,
y desde la lista arrastrás el sample directo a Ableton (o a cualquier DAW).

## Cómo ordena la librería

Cada dato se completa con la fuente más confiable disponible. El tooltip de cada fila muestra
de dónde salió cada dato:

| Fuente | Qué aporta | Confiabilidad |
|---|---|---|
| `meta`: chunk `acid` del WAV | BPM y one-shot | Alta |
| `name`: nombre del archivo y carpetas | BPM, key, instrumento, loop / one-shot | Alta en packs comerciales |
| `audio`: análisis con librosa | Duración, tipo, BPM, key, instrumento de one-shots | Media |

- **Tipo:** dura menos de 1,5 s, o tiene pocos ataques fuertes → one-shot. Si no → loop.
- **BPM:** el tempo detectado se corrige con el largo del loop. Si dura un número entero de
  compases, ese BPM es exacto y además arregla el error de doble o mitad de tempo. A los
  sonidos sostenidos (pads, drones) no se les inventa tempo.
- **Key:** perfil cromático comparado con los perfiles de Krumhansl-Kessler. No se calcula
  para baterías.
- **Instrumento:** diccionario de sinónimos (`bd`/`kick`, `vox`/`vocal`…). Mira primero el
  nombre del archivo y después las carpetas, de la más profunda a la más alta. Para one-shots
  sin nombre útil hay una heurística espectral (kick / bajo / hi-hat / percusión).

La base es SQLite, en `%APPDATA%\SampleScout\library.db`. Los re-escaneos solo procesan
archivos nuevos o modificados.

## Uso

- **Agregar carpeta…** indexa y analiza en segundo plano.
- Al hacer clic en un sample se escucha (`Espacio` reproduce o detiene).
- Arrastrá una o varias filas a Ableton.
- Clic derecho → mostrar en el Explorador o copiar la ruta.

## Desarrollo

Requiere **Python 3.12 x64**. En Windows ARM64 no hay paquetes nativos de `numba` ni `soxr`,
pero la versión x64 corre emulada sin problema.

```bash
uv venv --python cpython-3.12-windows-x86_64-none .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python -m sample_scout
.venv/Scripts/python -m pytest
```

`SAMPLE_SCOUT_DB=ruta\otra.db` usa otra base, útil para pruebas.

## Próximos pasos

1. **Clasificación con un modelo** (PANNs o CLAP) para instrumentos de loops y material
   propio, en reemplazo de la heurística.
2. **"Sonidos parecidos"** con embeddings y vecinos más cercanos.
3. **Búsqueda por texto libre** con CLAP ("kick oscuro con punch").
4. Preescucha sincronizada al tempo del proyecto y filtro por tonalidad relativa.
5. Empaquetado con PyInstaller como `.exe`.
