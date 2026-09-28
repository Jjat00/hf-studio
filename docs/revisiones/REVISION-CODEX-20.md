# Revisión adversarial del árbol sin commit sobre `da4c3a8`

Fecha: 2026-09-28. Alcance: los cuatro hallazgos de `REVISION-CODEX-19.md` y el diff sin commit, incluidos lanzador, puesta en marcha, CLI, pruebas, README, instrucciones para agentes y CI. No conecté agentes, generé contenido ni arranqué servicios en los puertos 8787 o 3000.

## Hallazgos

1. **[P2] En Windows sigue habiendo una carrera que puede dejar vivo a Next.** `src/hf_studio/launcher.py:93-98` ejecuta `pnpm` con `Popen` y solo después llama a `AssignProcessToJobObject`. Si `pnpm` crea un hijo durante ese intervalo, el hijo ya creado no entra retroactivamente en el job. Si la asignación del padre sí tiene éxito, `stop()` ejecuta solo `TerminateJobObject` (`launcher.py:103-108`) y deja fuera a ese hijo. Si el padre además termina antes de la asignación, el código vuelve a `taskkill /T` sobre su PID ya inactivo, el caso de la revisión 19. La [documentación de Microsoft sobre `AssignProcessToJobObject`](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject) indica que los hijos se asocian por defecto al job del padre **cuando se crean**; el código no garantiza que la asociación ocurra antes de que `pnpm` cree a Next. La prueba de `tests/test_launcher.py:60-76` pasa en la ejecución nativa comunicada, pero depende del orden en que se planifiquen los procesos y no fuerza el caso anterior. Para garantizar el cierre, hay que impedir que `pnpm` ejecute hijos hasta estar asignado al job, por ejemplo, creándolo suspendido, asociándolo y reanudándolo.

## Comprobaciones

- **Revisión 19, hallazgo 1:** `setup.shell_join` usa comillas simples de PowerShell en Windows, duplica las comillas simples internas y encierra las rutas con `%`, `$`, `&` o `^` (`setup.py:161-169`). `connect` indica «Run this in PowerShell» (`setup.py:226-228`). `tests/test_setup.py:104-113` cubre esos caracteres y rutas con espacios. Resuelto.
- **Revisión 19, hallazgo 2:** `_WindowsJob` configura `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `UI.stop()` usa `TerminateJobObject` y, cuando falta el job, conserva `taskkill /T` (`launcher.py:18-117`). La prueba exclusiva de Windows comprueba por PID que el hijo muere después de que salga el padre; según la evidencia aportada, corrió y pasó en Windows nativo. Persiste la carrera descrita arriba, por lo que la garantía para todos los hijos no está resuelta.
- **Revisión 19, hallazgo 3:** `UI.watch` trata cualquier salida no pedida, incluido el código 0, como caída; marca el evento y señala `SIGINT` (`launcher.py:119-125`). La prueba parametrizada cubre 0 y 3 (`tests/test_launcher.py:24-30`). Resuelto.
- **Revisión 19, hallazgo 4:** creación de la UI, vigilante, mensajes y llamada a Uvicorn están dentro del mismo `try`; el `finally` ejecuta `ui.stop()` (`launcher.py:150-170`). Resuelto para la interrupción temprana descrita en la revisión 19.
- **Resto del diff:** revisé la CLI y la conexión MCP, las 25 pistas y títulos de herramientas, las pruebas nuevas, los scripts de inicio, README en ambos idiomas, `AGENTS.md`, `SECURITY.md` y la matriz de CI. No encontré otra regresión funcional demostrable. Los README todavía dicen que hubo 13 revisiones, un dato editorial desactualizado que no afecta al arranque.
- **Pruebas pedidas:** `.venv/bin/pytest -q`: **152 passed, 1 skipped** en Linux. `.venv/bin/ruff check src tests`: **All checks passed**. `git diff --check`: sin errores. `UV_CACHE_DIR=/tmp/hf-studio-uv-cache uv lock --check --offline`: correcto. No repetí la prueba de arranque nativo en Windows ni la del puerto ocupado; tomo los resultados comunicados, **148 passed, 5 skipped** y cierre correcto al ocupar 3000, como evidencia de esas ejecuciones, no de la secuencia de carrera.
- Solo añadí este informe. No modifiqué código ni documentación del producto.

## Veredicto

**CAMBIOS REQUERIDOS.** Los hallazgos 1, 3 y 4 de la revisión 19 quedaron resueltos. El Job Object corrige el cierre en el caso probado, pero la asignación posterior al inicio de `pnpm` no garantiza que todos sus hijos pertenezcan al job. El cierre de Next en Windows sigue dependiendo de una carrera de planificación.
