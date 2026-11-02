# Changelog

Los cambios de cada versión publicada. `tools/release.ps1` usa la sección de la versión como
notas del release en GitHub, así que cada versión tiene que tener su entrada antes de publicarse.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versionado
[semántico](https://semver.org/lang/es/).

## [Sin publicar]

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
