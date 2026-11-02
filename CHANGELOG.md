# Changelog

Los cambios de cada versión publicada. `tools/release.ps1` usa la sección de la versión como
notas del release en GitHub, así que cada versión tiene que tener su entrada antes de publicarse.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado
- Favoritos: tecla `F`, clic en la ☆ o clic derecho, y filtro "Solo favoritos".
- Estrellas de 0 a 5: teclas `0`–`5`, clic en la columna o clic derecho; columna ordenable y
  filtro por mínimo.
- Colecciones: crear, renombrar y borrar desde el panel "Biblioteca"; agregar con clic derecho
  o arrastrando filas sobre la colección; un sample puede estar en varias.
- Historial con los últimos 200 samples escuchados, en orden de escucha.
- Edición manual de tipo, instrumento, BPM y key de uno o varios samples (`F2`). Lo editado
  queda con fuente `user`, gana sobre las demás y re-escanear no lo pisa; "Restablecer datos
  automáticos" lo deshace.
- Tags libres: agregar y quitar desde el mismo diálogo, filtro por tag y búsqueda de texto que
  también los encuentra.

### Cambiado
- La base pasa al esquema 2 (se migra sola, sin perder datos). Los datos del usuario se guardan
  por ruta, aparte del índice, y sobreviven a quitar y volver a agregar una carpeta.
- Al recargar la lista se conservan la selección, la posición y el orden elegido por columna.

### Documentación
- README completo: uso, cómo se ordena la librería, actualizaciones, datos, solución de
  problemas, desarrollo y publicación.
- Docstrings en todas las funciones públicas.
- `tools/make_test_samples.py` y `tools/fake_release.py` para probar el análisis y la
  actualización sin publicar.
- `release.ps1` toma las notas del release de este archivo.

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
