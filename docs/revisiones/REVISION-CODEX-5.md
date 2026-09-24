# Revisión adversarial, ronda 5

Fecha: 2026-09-24. Revisado `HEAD` (`f47df64`) con `git show` y el código actual. No se modificó código.

## Resultado

No encontré defectos nuevos ni pendientes que exijan cambios. `src/hf_studio/mcp_server.py:193-242` protege con el mismo `threading.Lock` la emisión, limpieza, validación y asignación de clave de cada cotización. Así, dos canjes concurrentes del mismo `quote_id` no pueden aceptar claves de idempotencia distintas; el reintento con la clave ya asignada sigue permitido.

La prueba `tests/test_mcp_cost.py:87-119` fuerza el entrelazado. Con el lock, pasa. Sustituí `_quotes_lock` por un contexto vacío solo en un proceso de prueba, sin editar archivos: la prueba falló porque aceptó **8 claves** en vez de 1. Esto confirma que detecta la carrera corregida.

Verificaciones: `uv run pytest -q` **36 passed**; `npx tsc --noEmit` y `pnpm lint` desde `web/`, sin errores; `uv run ruff check src tests`, sin errores. La pérdida de cotizaciones al reiniciar el proceso MCP queda cubierta por el flujo previsto de recotizar.

## Veredicto

**APROBADO**
