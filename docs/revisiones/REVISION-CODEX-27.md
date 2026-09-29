# Revisión adversarial 27 del árbol sin commit sobre `02e7e75`

Fecha: 2026-09-28. Alcance: todo el diff respecto a `02e7e75` y los hallazgos de `REVISION-CODEX-26.md`. No hice llamadas de generación, no ejecuté `hf-studio connect`, no arranqué servidores en 8787 ni 3000, no borré `web/.next`, no leí `.env` ni `.env.swp` y no modifiqué código.

## Hallazgos

No encontré hallazgos bloqueantes ni regresiones en el diff revisado.

## Comprobación de la revisión 26

1. **Windows con agente en WSL:** [la página MCP](../../web/src/app/mcp/page.tsx) añade `askWsl` al prompt cuando Next corre en Windows desde una ruta con letra de unidad. [Los textos español e inglés](../../web/src/lib/i18n/dictionaries.ts) indican expresamente que el agente en WSL no use la instalación de Windows, que pida clonar y arrancar HF Studio dentro de WSL y que use esa copia. La ruta `/mnt/<unidad>/...` aparece solo para identificar la carpeta de Windows; los comandos no la usan como directorio de `uv` en WSL. Esto resuelve el caso de la revisión 26 con red NAT predeterminada. No comprobé el flujo en Windows o WSL nativos.
2. **Lecturas POSIX partidas:** [la prueba nueva](../../tests/test_setup.py) abre una PTY, inicia un proceso hijo que llama a `masked_input()`, envía los marcadores en cinco escrituras separadas y exige que la clave devuelta sea exactamente `id:secret`. El caso que simulaba Windows con bloques supuestamente POSIX ya no está en la parametrización.
3. **Archivos sensibles de intercambio:** [.gitignore](../../.gitignore) excluye `.env.*`, `*.swp` y `*.swo`, conserva la excepción `!.env.example` y `git check-ignore -v .env.swp` confirma que el swap queda ignorado. `.env.example` y `web/.env.example` siguen versionados.
4. **Comandos manuales en Windows:** [el encabezado de la página](../../web/src/app/mcp/page.tsx) añade «PowerShell» cuando corre en Windows. Cada cliente conserva un bloque de copia independiente.

## Comprobaciones

- `.venv/bin/pytest -q`: **166 passed, 2 skipped**.
- `.venv/bin/ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `npx tsc --noEmit`: ambos terminaron con código 0.
- `git diff --check 02e7e75`: sin errores.
- Revisé los cambios en CLI, setup, pruebas, `dev.cmd`, README, `.gitignore` y UI. La validación de Windows y WSL fue estática; no hice una prueba manual del producto.

## Veredicto

**APROBADO.** Los tres hallazgos de la revisión 26 están resueltos para los casos descritos y no encontré regresiones bloqueantes en el resto del diff.
