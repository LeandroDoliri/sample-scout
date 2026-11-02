# Changelog

Los cambios de cada versión publicada. `tools/release.ps1` usa la sección de la versión como
notas del release en GitHub, así que cada versión tiene que tener su entrada antes de publicarse.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado
- Funciones de IA opcionales y locales (CLAP de LAION, Apache-2.0): botón **IA** →
  *Activar funciones de IA…* baja el modelo una vez (~195 MB, con avance, cancelar y
  reintentos), lo verifica con sha256 y lo guarda en `%LOCALAPPDATA%\SampleScout\models`.
  Sin el modelo la app anda igual que antes.
- La app escucha cada sample en segundo plano después del análisis (un solo proceso, ~0,15 s
  por sample) y guarda una huella de sonido por ruta, que se recalcula solo si el archivo cambia.
- **Sonidos parecidos** (clic derecho, `Ctrl+P` o el panel de detalle): vista con los 100 más
  parecidos, que se puede seguir filtrando.
- **Búsqueda por sonido**: "kick oscuro con punch", "redoblante crujiente"… Traduce sola los
  términos de producción en español.
- Desactivar las funciones de IA o borrar el modelo desde el mismo botón.

### Cambiado
- La base pasa al esquema 4 (tabla de embeddings); las bases anteriores se actualizan solas.
- Dependencias nuevas: `onnxruntime` y `tokenizers` (las instala la actualización desde la app).
- La búsqueda de actualizaciones ignora los releases que no son de la app (prerelease o tags
  que no son `vX.Y.Z`, como el del modelo).

## [0.2.0] - 2026-11-02

### Agregado
- Favoritos: tecla `F`, clic en la ☆ o clic derecho, y filtro "Solo favoritos".
- Estrellas de 0 a 5: teclas `0`–`5`, clic en la columna o clic derecho; columna ordenable y
  filtro por mínimo.
- Colecciones: crear, renombrar y borrar desde el panel "Biblioteca"; agregar con clic derecho
  o arrastrando filas sobre la colección; un sample puede estar en varias.
- Historial con los últimos 200 samples escuchados, en orden de escucha.
- Edición manual de tipo, instrumento, BPM y key de uno o varios samples (`F2`). Lo editado
  gana sobre lo que detecta la app y volver a escanear no lo pisa; "Restablecer datos
  automáticos" lo deshace.
- Tags libres: agregar y quitar desde el mismo diálogo, filtro por tag y búsqueda de texto que
  también los encuentra.
- Portada del sample pack: se detecta al escanear (la imagen más cercana hasta la carpeta
  agregada) y se muestra en un panel de detalle a la derecha y como miniatura en cada fila.
  Las imágenes se cargan en segundo plano.
- Columnas a elección: clic derecho en el encabezado para mostrar u ocultar cada una o
  restablecerlas, y arrastre para reordenarlas. Visibilidad, orden y ancho se recuerdan entre
  aperturas; las columnas que sume una versión nueva aparecen a la vista.
- Forma de onda del sample elegido en el panel de detalle, con el cursor de reproducción; clic
  sobre la onda para reproducir desde ese punto. Se calcula una vez y queda guardada.
- Columna opcional "Onda" (mini forma de onda por fila), oculta de entrada.
- Filtro por duración (rango en segundos) en el panel izquierdo.
- Duplicados: vista "Duplicados" en el panel "Biblioteca" con los archivos repetidos agrupados
  (aunque estén en otras carpetas o con otro nombre), lista de copias en el panel de detalle
  para ir a cada una y filtro "Ocultar duplicados". La app no borra ni mueve archivos.

### Cambiado
- La librería se actualiza sola al abrir la versión nueva, sin perder nada ni re-analizar lo
  ya analizado. La forma de onda y la detección de duplicados se calculan en segundo plano para
  los samples que ya tenías.
- Favoritos, estrellas, colecciones, tags y ediciones se guardan aparte del índice y sobreviven
  a quitar y volver a agregar una carpeta.
- Al recargar la lista se conservan la selección, la posición y el orden elegido por columna.

### Documentación
- README completo: uso, cómo se ordena la librería, actualizaciones, datos, solución de
  problemas, desarrollo y publicación.
- Herramientas para probar el análisis y la actualización sin publicar (para desarrollo).

## [0.1.0] - 2026-11-01

Primera versión.

### Agregado
- Indexado de carpetas en SQLite, sin mover ni modificar los archivos, con re-escaneo
  incremental.
- Datos desde el nombre y las carpetas: BPM, tonalidad, instrumento, loop / one-shot.
- Lectura del chunk `acid` de los WAV.
- Análisis de audio con librosa: tipo, BPM corregido por el largo del loop, tonalidad e
  instrumento de one-shots de batería.
- Ventana con filtros (instrumento, tipo, BPM, key, texto), preescucha y arrastre a Ableton.
- Instalador de Windows sin permisos de administrador y actualización con un clic desde
  GitHub Releases.
