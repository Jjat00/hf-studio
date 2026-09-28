# Revisión adversarial 24 del árbol sin commit sobre `439ffdb`

Fecha: 2026-09-28. Alcance: todo el diff respecto a `HEAD`, incluido el arreglo solicitado en [REVISION-CODEX-23.md](REVISION-CODEX-23.md), CI, arranque, pruebas y documentación. No generé contenido, gasté créditos, conecté agentes ni arranqué servidores en los puertos 8787 o 3000. No borré `web/.next` ni modifiqué código.

## Hallazgos

No encontré regresiones bloqueantes. **El hallazgo de la revisión 23 quedó resuelto:** en macOS, `check_ffmpeg()` detecta el directorio de Homebrew que contiene `ffmpeg-full`, lo mueve al primer lugar de `PATH` aunque ya estuviera presente y elimina su aparición anterior. Por tanto, con `PATH=regular:full`, `shutil.which("ffmpeg")` selecciona el ejecutable de `full`. La prueba usa archivos ejecutables reales de mentira para `ffmpeg` y `ffprobe` en ambos directorios, sin sustituir `shutil.which`, y confirma que `full` aparece una sola vez y que no sale el aviso sobre `rubberband`.

**Observación menor sobre la cobertura:** la prueba afirma explícitamente la ruta de `ffmpeg`, pero no la de `ffprobe`; además, comprueba que la salida no contenga `rubberband`, en vez de exigir que esté vacía. Con los dos ejecutables presentes en `full` y ese directorio al principio de `PATH`, el código actual también resuelve `ffprobe` allí y no imprime ningún aviso. Estas aserciones más estrechas no ocultan una regresión presente en el diff, pero convendría ampliarlas si se vuelve a tocar esta función.

## Comprobaciones

- `.venv/bin/pytest -q`: **155 passed, 2 skipped**.
- `.venv/bin/ruff check src tests`: **All checks passed**.
- `git diff --check HEAD`: sin errores.
- CI instala `ffmpeg-full` en macOS y añade su `bin` a `GITHUB_PATH`; conserva las rutas de Linux y Windows. En la tarea web, `pnpm exec next typegen` precede a `tsc --noEmit`, como requería el fallo de `RouteContext` documentado en la revisión 23.
- `README.md`, `README.es.md` y `AGENTS.md` coinciden en el requisito de `ffmpeg-full` para macOS y en la secuencia de comprobación de tipos. `serve` ejecuta la misma comprobación de ffmpeg que `start`.
- No ejecuté el CI ni hice una prueba nativa en macOS o Windows con este árbol. La prueba nueva simula macOS y comprueba la búsqueda real de ejecutables en un `PATH` temporal.

## Veredicto

**APROBADO.** La prioridad de `ffmpeg-full` que falló en la revisión 23 está corregida y el resto del diff no introduce una regresión detectable en esta revisión.
