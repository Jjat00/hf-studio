# Revisión adversarial, ronda 4

Fecha: 2026-09-24. Revisado `93397cd` con `git show` y el código actual. Solo se creó este informe.

## Hallazgos

1. **Alta. Dos llamadas concurrentes pueden gastar la misma cotización con claves distintas.** `src/hf_studio/mcp_server.py:212-238` comprueba `q["key"]` y después lo asigna sin sincronización. Las herramientas síncronas del servidor MCP se ejecutan en hilos (`mcp/server/mcpserver/resolve.py`, `anyio.to_thread.run_sync`), por lo que dos llamadas a `generate` o `generate_batch` pueden leer `None` antes de que cualquiera escriba su clave. Reproduje ese entrelazado en dos hilos: el mismo `quote_id` aceptó las claves `first` y `second` y envió ambas generaciones. La API deduplica por clave, así que claves distintas permiten dos cargos. **Arreglo propuesto:** proteger lectura, validación y asignación de la cotización con un `threading.Lock` común, o hacer esa operación atómica. Añadir una prueba concurrente que exija que solo una clave sea aceptada.

## Arreglos comprobados

- El `quote_id` es aleatorio, vence a los 15 minutos, liga la petición y conserva el precio que se mostró. No se recotiza al generar. En uso secuencial, una clave nueva para la misma cotización se rechaza y un reintento con la clave original llega a la API, que deduplica. Perder las cotizaciones al reiniciar el proceso stdio se resuelve recotizando, conforme al diseño indicado.
- “Dance transfer” cotiza y genera con `run_preset`; README y la página MCP explican `quote_id`. Los hints por ítem llegan a `quote()` en el API y siguen validándose como positivos y finitos.
- `UV_CACHE_DIR=/tmp/hf-review-uv-cache uv run pytest -q`: **35 passed**. Desde `web/`, `npx tsc --noEmit` y `pnpm lint`: sin errores. `uv run ruff check src tests`: sin errores. Las pruebas actuales no cubren canjes concurrentes.

## Veredicto

**CAMBIOS REQUERIDOS**
