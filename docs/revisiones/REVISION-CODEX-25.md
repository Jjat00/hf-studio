# Revisión adversarial 25 del árbol sin commit sobre `02e7e75`

Fecha: 2026-09-28. Alcance: diff respecto a `HEAD`, con atención a la entrada de claves en Windows y al prompt MCP. No hice llamadas de generación, no ejecuté `connect`, no arranqué servidores en 8787 ni 3000, no borré `web/.next` ni modifiqué código.

## Hallazgos

1. **[P1] El prompt MCP falla si la UI corre en Windows y el agente corre en WSL.** [La página](../../web/src/app/mcp/page.tsx) toma `path.resolve(process.cwd(), "..")` del proceso de Next y [el texto](../../web/src/lib/i18n/dictionaries.ts) lo inserta literalmente en `uv run --directory "${root}" ...` y en `${root}/AGENTS.md`. Con el caso indicado, repo en `D:\Projects\hf-studio`, el agente en WSL recibe una ruta `D:\...` que `uv` en Linux no reconoce; tampoco puede leer el `AGENTS.md` indicado. El prompt promete funcionar al pegarlo en Claude Code o Codex sin preguntar dónde corren. Debe indicar la traducción de la ruta para agentes en WSL o proporcionar ambas rutas cuando sea posible. Este hallazgo es condicional a usar el agente en WSL; con agente y UI nativos de Windows, la ruta generada sí corresponde al mismo sistema.

2. **[P2] El filtro ANSI no funciona como flujo.** [`feed()`](../../src/hf_studio/setup.py) aplica `_ANSI.sub()` a cada lectura aislada. En Windows, `msvcrt.getwch()` entrega un carácter por llamada, de modo que nunca llega a la regex una secuencia ANSI completa. Simulé esa rama con `\x1b[200~id:secret\x1b[201~\r`: `masked_input()` devolvió `'[200~id:secret[201~'` y mostró 19 asteriscos en vez de los 9 de la clave. En POSIX también falla cuando `os.read()` divide la secuencia entre dos bloques; por ejemplo, `['\x1b[20', '0~id:secret\x1b[201~']` conserva el primer marcador. Esto provoca 401 y consume intentos si el host entrega marcadores de pegado. **No comprobé en Windows nativo** si Ctrl+V o clic derecho en Windows Terminal o conhost entregan esos marcadores con la configuración habitual; la reproducción demuestra que la protección ANSI declarada no los tolera cuando aparecen.

3. **[P2] Los comandos del prompt no escapan la ruta para la shell.** [Las plantillas](../../web/src/lib/i18n/dictionaries.ts) ponen `${root}` entre comillas dobles. En PowerShell, una ruta legal con `$` puede expandirse; en shells POSIX, `$` y sustituciones de comandos se evalúan dentro de esas comillas. La misma ruta aparece sin protección en el paso de lectura de `AGENTS.md`. En cambio, [`shell_join()`](../../src/hf_studio/setup.py) ya emite comandos de registro con comillas adecuadas para PowerShell o POSIX. Con `D:\Projects` no se manifiesta, pero el prompt generado no es seguro para cualquier ubicación real del repo.

**Observación de uso:** [el bloque «Terminal»](../../web/src/app/mcp/page.tsx) reúne cuatro comandos alternativos en un solo botón de copiar. Al pegarlo entero en una terminal se registran Claude Code y Codex y se crean además las claves de las dos variantes JSON, aunque el usuario solo quisiera conectar un cliente. Conviene separar las opciones para que «Copiar» entregue solo la elegida.

## Comprobaciones

- `.venv/bin/pytest -q`: **162 passed, 2 skipped**.
- `.venv/bin/ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `npx tsc --noEmit`: ambos terminaron con código 0.
- `git diff --check HEAD`: sin errores.
- Confirmé en código que `connect json` imprime configuración, que `uv run --directory` existe, que `/health` devuelve `ok: true` y que el lanzador inicia Next con `cwd=ROOT/web`. La ruta de la UI es correcta para un agente en el mismo sistema y el flujo de reintento tras 401 queda cubierto por la suite.
- No probé el pegado en PowerShell, Windows Terminal ni conhost nativos. La prueba Windows existente simula teclas sueltas y una flecha, pero no un pegado con marcadores ni el cruce Windows/WSL.

## Veredicto

**CAMBIOS REQUERIDOS.** El flujo habitual con `D:\Projects` y agente nativo puede funcionar, pero el prompt anunciado para los agentes falla en WSL y el filtro de secuencias de pegado no cumple lo que declara. Las pruebas verdes no cubren esos casos.
