# Revisión adversarial 26 del árbol sin commit sobre `02e7e75`

Fecha: 2026-09-28. Alcance: todo el diff respecto a `HEAD` y los cuatro puntos de `REVISION-CODEX-25.md`. No hice llamadas de generación, no ejecuté `hf-studio connect`, no arranqué servidores en 8787 ni 3000, no borré `web/.next` ni modifiqué código.

## Hallazgos

1. **[P1] El caso Windows → WSL aún falla con la red NAT predeterminada.** [La página](../../web/src/app/mcp/page.tsx) sí añade la ruta `/mnt/<unidad>/...` al prompt cuando Next corre en Windows. Sin embargo, [el prompt](../../web/src/lib/i18n/dictionaries.ts) ordena comprobar `http://127.0.0.1:8787/health` y [`connect` fija esa misma URL](../../src/hf_studio/setup.py) para el MCP. [El lanzador](../../src/hf_studio/launcher.py) liga la API de Windows exclusivamente a `127.0.0.1`. Según la [documentación de red de WSL de Microsoft](https://learn.microsoft.com/windows/wsl/networking), en el modo NAT predeterminado un proceso Linux no llega a un servidor Windows mediante su propio `127.0.0.1`; esa comunicación por localhost requiere el modo de red reflejada. Usar la IP del host tampoco basta con el servidor ligado solo a loopback. Por tanto, la traducción de la ruta resuelve la ubicación del repo, pero no permite completar ni usar la conexión MCP en la configuración WSL predeterminada. Hay que indicar una configuración de red que funcione o ejecutar la API del lado de WSL.

2. **[P2] El caso parametrizado «partido entre lecturas (POSIX)» no prueba lecturas POSIX.** En [`test_paste_markers_and_arrows_never_reach_the_key`](../../tests/test_setup.py), todos los casos pasan por `iter("".join(chunks))`, simulan `msvcrt.getwch()` y fuerzan `os.name = "nt"`. La lista de bloques POSIX se concatena antes de entrar en `masked_input()`, así que la suite no detectaría una regresión exclusiva de `os.read()` o de la conservación del estado entre bloques. La implementación actual sí conserva el estado fuera de `feed()`: una comprobación adicional con una PTY POSIX real y los cuatro bloques separados devolvió `id:secret`, mostró nueve asteriscos y no imprimió la clave. Falta que el test automatizado cubra lo que declara.

**Riesgo del árbol, fuera del diff:** `git status` muestra `.env.swp` sin seguimiento; `git check-ignore` confirma que no está excluido. Mide 12.288 bytes y contiene los nombres `HF_API_KEY` y `ELEVENLABS_API_KEY`. No inspeccioné ni imprimí sus valores. Al ser un swap de `.env`, debe quedar fuera de cualquier commit para evitar una posible filtración de credenciales.

## Comprobación de los puntos de la revisión 25

- **Ruta WSL:** la página calcula `/mnt/<unidad>/...` para una ruta Windows con letra de unidad y la inserta mediante `askWsl`. Queda la limitación de red del hallazgo 1.
- **`masked_input`:** `escape` vive entre llamadas a `feed()`; se descartan CSI, SS3 y ESC más una tecla. Las pruebas parametrizadas cubren marcadores 200~/201~ y flechas en la rama Windows. La prueba adicional con PTY confirmó el caso POSIX dividido. Queda el hueco de cobertura automatizada del hallazgo 2.
- **Rutas literales:** la página usa comillas simples con `''` para PowerShell y `'\''` para POSIX; los README usan comillas simples. El paso 4 ya dice «el AGENTS.md de esa carpeta». Comprobé que una ruta POSIX con espacio, apóstrofo, `$HOME` y sustitución de comandos queda literalmente citada.
- **Comandos manuales:** hay cuatro `CopyBlock` separados, cada uno con su botón de copiar. Los comandos están preparados para PowerShell en Windows; la página no nombra esa shell y los comentarios `#` de los bloques JSON tampoco son comentarios de `cmd.exe`.

## Comprobaciones

- `.venv/bin/pytest -q`: **166 passed, 2 skipped**.
- `.venv/bin/ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `npx tsc --noEmit`: ambos terminaron con código 0.
- `git diff --check HEAD`: sin errores.
- Revisé el diff completo, incluidos `cli.py`, `setup.py`, `dev.cmd`, los README y la UI. No probé Windows ni WSL nativos, ni realicé llamadas a la API.

## Veredicto

**CAMBIOS REQUERIDOS.** El prompt sigue sin funcionar para un agente en WSL con la red predeterminada cuando la API corre en Windows. Además, la prueba de bloques POSIX debe ejecutar realmente esa rama y el swap de `.env` no debe entrar en un commit.
