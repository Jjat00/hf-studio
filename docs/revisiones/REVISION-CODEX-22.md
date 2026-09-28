# Revisión adversarial del árbol sin commit sobre `da4c3a8`

Fecha: 2026-09-28. Alcance: el hallazgo de `REVISION-CODEX-21.md` y todo el diff sin commit, incluidos los archivos nuevos de lanzador, puesta en marcha, CLI, MCP, pruebas, documentación y CI. No conecté agentes, generé contenido ni arranqué servicios en los puertos 8787 o 3000.

## Hallazgos

No encontré regresiones funcionales demostrables ni hallazgos que requieran cambios.

## Comprobaciones

- **Hallazgo de la revisión 21 resuelto:** `_WindowsJob.resume()` declara `ResumeThread.restype` como `DWORD`, cuenta las llamadas cuyo retorno no es `0xFFFFFFFF` y eleva `OSError` si no logró reanudar ningún hilo (`src/hf_studio/launcher.py:93-120`). `UI.__init__` llama a `stop()` y relanza el error (`launcher.py:141-150`); `start` lo comunica por stderr y devuelve 1 antes de anunciar o arrancar la API (`launcher.py:207-215`).
- **Cobertura del fallo:** la prueba nativa de Windows inyecta un `OSError` en `resume()` y comprueba que el proceso creado ya terminó (`tests/test_launcher.py:96-113`). Otra prueba comprueba el código 1 y el aviso de `start` (`tests/test_launcher.py:85-93`). En Linux se ejecutó esta segunda prueba; la primera queda omitida por plataforma.
- **Pruebas nativas de Windows comunicadas por Jaime:** 150 passed y 5 skipped. Una corrida anterior, bajo carga, falló de forma intermitente en `tests/test_audio.py::test_shorter_source_audio_never_cuts_the_video`; pasó al repetirla sola y en la suite posterior. Ni esa prueba ni el código correspondiente cambiaron en este diff. Tomo estos resultados como evidencia aportada, no como pruebas repetidas aquí.
- **Resto del diff:** revisé la puesta en marcha y limpieza de procesos, `setup.py`, CLI, contratos y pistas de las 25 herramientas MCP, scripts de arranque, pruebas, documentación y CI. No encontré otra regresión funcional demostrable.
- **Pruebas pedidas en Linux:** `.venv/bin/pytest -q`: **153 passed, 2 skipped**. `.venv/bin/ruff check src tests`: **All checks passed**. `git diff --check`: sin errores. `UV_CACHE_DIR=/tmp/hf-studio-review22-uv-cache uv lock --check`: correcto.
- Solo añadí este informe. No modifiqué código ni documentación del producto.

## Veredicto

**APROBADO.** El fallo de reanudación de la revisión 21 queda tratado con cierre del proceso y error visible para el usuario. El resto del árbol sin commit no mostró regresiones en esta revisión.
