# Revisión adversarial del árbol sin commit sobre `da4c3a8`

Fecha: 2026-09-28. Alcance: `git status`, `git diff`, archivos nuevos y los tres hallazgos de `REVISION-CODEX-16.md`; también revisé los demás cambios del árbol. No ejecuté `hf-studio connect` ni hice generaciones reales.

## Hallazgos

1. **[P2] La documentación de `--print` todavía omite la configuración JSON y no cumple el texto solicitado en los cuatro lugares.** La ayuda de `src/hf_studio/cli.py:165-169` sí dice «command or config (with a new key)», coherente con `src/hf_studio/setup.py:179-189`: `claude-desktop` y `json` imprimen una configuración con `HF_STUDIO_TOKEN` nuevo. Sin embargo, `README.md:125`, `README.es.md:137-138` y `AGENTS.md:19-21` dicen que `--print` imprime *el comando*. Los README muestran antes los ejemplos de JSON, pero la explicación específica de `--print` sigue siendo falsa para esos dos clientes. Cambiarla a «comando o configuración con una clave nueva» en ambos README y `AGENTS.md`.

2. **[P2] Los pasos de conexión aún prometen un registro que puede no ocurrir cuando falta la CLI.** `setup.connect` avisa expresamente «nothing was registered» y entrega un comando con la clave nueva (`src/hf_studio/setup.py:190-207`), de modo que la salida interactiva corrige la parte funcional del hallazgo 16. Pero devuelve `0` en ese caso (`:207`), mientras `README.md:116-125`, `README.es.md:128-138` y `AGENTS.md:19-22` presentan `connect` como un comando que registra al agente; los README solo añaden que imprime un comando si falta la CLI y ninguno dice que entonces no se registró nada. Una automatización que se guíe por el código de salida puede concluir erróneamente que el MCP está conectado. Documentar explícitamente que en esa ruta no hay registro automático y que hay que ejecutar el comando impreso donde exista la CLI; si se quiere prometer éxito solo tras el registro, devolver fallo para esa ruta.

3. **[P2] La configuración para Claude Desktop en Windows no es utilizable cuando `connect` corre en WSL.** `src/hf_studio/setup.py:161-162,179-189` imprime `"command": "uv"` con `--directory` apuntando a la ruta Linux de `ROOT` (`/home/...`). Claude Desktop, instalado en Windows en este entorno, ejecuta esa configuración en Windows, donde la ruta Linux no existe y `uv` no lanza el proceso de WSL. La clave nueva sí es válida, pero pegar el JSON anunciado en `claude_desktop_config.json` no conecta el servidor. La configuración debe invocar WSL con una ruta o lanzador accesible desde Windows, o acotar en la documentación que el JSON solo sirve si cliente y servidor corren en el mismo sistema. `tests/test_setup.py` solo inspecciona que el JSON contiene la clave y `mcp`; no cubre esta compatibilidad.

## Comprobaciones

- **Hallazgo 1 de la revisión 16:** `_connect` crea una clave nueva incluso con `--print`; la configuración JSON impresa incorpora esa clave activa. La ayuda de CLI quedó corregida. Persisten las tres discrepancias de documentación y el problema de compatibilidad con Claude Desktop en Windows descritos arriba.
- **Hallazgo 2:** la ausencia de `claude` o `codex` produce el aviso explícito y un comando protegido con `shlex.join`, con la clave nueva. La documentación explica que se imprime el comando, pero no que el registro quedó pendiente. `tests/test_setup.py` comprueba el comando, aunque no el aviso, el retorno `0` ni la ejecución completa de `_connect` en esa ruta.
- **Hallazgo 3:** `setup.connect` captura `OSError` de `subprocess.run` y devuelve `1` (`src/hf_studio/setup.py:191-196`); `_connect` revoca la clave al recibir un código distinto de cero (`src/hf_studio/cli.py:145-152`). Hay pruebas para la excepción y para la revocación, aunque la segunda simula el código `1` en vez de recorrer ambas funciones juntas. La corrección funcional es consistente.
- **Resto del diff:** revisé instalación, permisos de secretos, comandos impresos, pistas MCP, sonoteca, documentación y CI. Fuera de la configuración Windows descrita arriba no encontré otra regresión funcional nueva. `git diff --check`: sin errores.
- **Pruebas pedidas:** `.venv/bin/pytest -q`: **145 passed**. `.venv/bin/ruff check src tests`: **All checks passed**. Las pruebas usan servicios simulados y no consumieron créditos.
- Solo añadí este informe; no modifiqué código ni documentación del producto.

## Veredicto

**CAMBIOS REQUERIDOS.** Las rutas de conexión corrigen los fallos funcionales de la revisión 16, pero la documentación de `--print` y del caso sin CLI aún contradice o deja incompleto el comportamiento real. Además, el JSON anunciado para Claude Desktop no sirve en el entorno Windows con servidor en WSL.
