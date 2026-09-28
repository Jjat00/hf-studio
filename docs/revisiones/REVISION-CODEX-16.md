# Revisión adversarial del árbol sin commit sobre `da4c3a8`

Fecha: 2026-09-28. Alcance: `git status`, `git diff`, archivos nuevos y los ocho hallazgos de `REVISION-CODEX-15.md`, con énfasis en `setup.py`, `cli.py`, `test_setup.py`, ambos README y `AGENTS.md`. No ejecuté `hf-studio connect` ni hice generaciones reales.

## Hallazgos

1. **[P2] `connect --print` sigue modificando el estado pese a prometer que solo muestra el comando.** `src/hf_studio/cli.py:137-146,190-191` omite la comprobación de registro con `--print`, pero siempre llama a `new_client_key`, que inserta y confirma un cliente activo (`src/hf_studio/setup.py:110-117`). Cada consulta crea `codex`, `codex-2` y sucesivos aunque no se registre nada. Ya no invalida una conexión existente, que era el daño principal del punto 1 de la revisión 15, pero `README.md:125`, `README.es.md:137`, `AGENTS.md:19-21` y la ayuda de CLI describen `--print` como una operación que solo muestra información. Los tests prueban `new_client_key` y la impresión por separado, no la ejecución completa de `_connect` con `install=False`. Hacer explícita la emisión de una clave al imprimir una configuración utilizable, o convertir `--print` en una consulta sin escritura.

2. **[P2] `connect` devuelve éxito cuando no existe el ejecutable del cliente y no registra el MCP.** `already_registered` devuelve `False` si `claude` o `codex` no está instalado (`src/hf_studio/setup.py:149-154`); `_connect` crea una clave y llama a `setup.connect` (`src/hf_studio/cli.py:145-152`). Si falta el ejecutable, `setup.connect` imprime un comando manual y devuelve `0` (`src/hf_studio/setup.py:189-199`). Por tanto, `hf-studio connect codex` puede terminar con código de éxito y una clave activa aunque Codex no haya recibido ningún servidor. `AGENTS.md:19-21` y ambos README presentan el comando como registro automático. `tests/test_setup.py:82-90` comprueba el texto impreso en este caso, pero no el código de salida ni el estado final. Devolver fallo para una instalación solicitada que no se hizo, o acotar con claridad la promesa y el estado que comunica la CLI.

3. **[P3] Una excepción al iniciar `mcp add` deja la clave nueva activa.** `setup.connect` solo transforma un código de salida distinto de cero en fallo (`src/hf_studio/setup.py:190-196`). Si `subprocess.run` lanza `OSError`, por ejemplo si el ejecutable desaparece entre `shutil.which` y su ejecución, la excepción salta el bloque de revocación de `_connect` (`src/hf_studio/cli.py:146-149`). El usuario ve un traceback y queda una clave sin registro. La promesa de revocar la clave al fallar el registro se cumple para salidas no nulas, pero no para errores al lanzar el proceso.

## Comprobaciones

- **Revisión 15:** la rotación de claves al usar `connect` quedó eliminada; `new_client_key` conserva las existentes y el retorno no nulo de `mcp add` revoca la nueva y devuelve `1`. `already_registered` solo acepta como ausencia explícita «No MCP server named». `copy_private` crea `.env` y `web/.env.local` con `0600`. `ensure_ui_key` comprueba `web-ui` activo, recupera `sees_all` y ajusta la URL local. `setup` y `connect` cambian a la raíz antes de leer configuración o base, y `ensure_env` acepta `HF_API_KEY` del entorno. La salida de shell usa `shlex.join`; ElevenLabs se ofrece al crear `.env` y ambos README explican cómo añadir su clave después. La prueba de `tests/test_voice.py` verifica que listar sonidos repone un audio terminado en la sonoteca. Los puntos 2, 3, 4, 6, 7 y 8 están resueltos; los puntos 1 y 5 conservan los casos descritos arriba.
- **Pruebas:** `.venv/bin/pytest -q`: **143 passed**. `.venv/bin/ruff check src tests`: **All checks passed**. `git diff --check`: sin errores. Las pruebas usan servicios simulados; no gasté créditos.
- Solo añadí este informe. No modifiqué código ni documentación del producto.

## Veredicto

**CAMBIOS REQUERIDOS.** Las correcciones principales de la revisión 15 funcionan, pero `--print` todavía crea claves activas al consultar y `connect` puede indicar éxito sin haber registrado el servidor. El camino de excepción al lanzar `mcp add` también necesita limpiar la clave creada.
