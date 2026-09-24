# Revisión adversarial, ronda 3

Fecha: 2026-09-24. Revisado el commit `5a6c0e9` con `git show` y el código actual. Solo se creó este informe.

## Hallazgos

1. **Alta. Un `quote_id` aprobado puede reutilizarse para nuevos cargos.** `src/hf_studio/mcp_server.py:189-203,225-269` recalcula una huella determinista, pero no registra consumo ni la ata a `idempotency_key`. El mismo `quote_id` de `estimate_cost` permite llamar dos veces a `generate` con `allow_duplicate=True` y claves distintas; ambas peticiones llegan a `/v1/generations`. El lote también admite el mismo `quote_id` con una nueva clave y puede generar todas las variantes otra vez. Lo reproduje con `_call` simulado: una cotización, dos llamadas de generación aceptadas. **Arreglo propuesto:** emitir cotizaciones de un solo uso o vincularlas a una clave de idempotencia; permitir únicamente reintentos con esa misma clave y la misma petición. Una nueva ejecución con gasto debe requerir una nueva cotización y un nuevo OK.

2. **Media. El tutorial MCP “Dance transfer” usa un `quote_id` incompatible con su siguiente paso.** `web/src/lib/use-cases.ts:217-220` pide `estimate_cost` para el modelo y luego `run_preset` para `dance-transfer`. La primera huella contiene `{model, input, hints}` (`src/hf_studio/mcp_server.py:91-98`); la segunda espera `{slug, variables, hints}` (`:274-292`). Aunque ambos importes sean idénticos, `run_preset(..., dry_run=False, quote_id=<id de estimate_cost>)` devuelve “Missing or stale quote_id”; lo reproduje con una API simulada. **Arreglo propuesto:** cotizar con `run_preset("dance-transfer", ..., dry_run=True, input_video_seconds=...)` y reutilizar su `quote_id`, o generar directamente con la cotización de `estimate_cost`.

3. **Media. Una variación del precio exacto entre las dos llamadas impide ejecutar una cotización recién aceptada.** `src/hf_studio/mcp_server.py:197-206` incluye `usd` y `credits` exactos en la huella; `generate`, `generate_batch` y `run_preset` vuelven a cotizar antes de compararla (`:112-115,252-262,283-292`). Si Higgsfield devuelve, por ejemplo, $1.01 en la cotización visible y $1.02 en la comprobación, el MCP rechaza el ID. Una simulación con esos dos importes reprodujo el rechazo. Es correcto detenerse ante un cambio de precio, pero el flujo no devuelve la cotización nueva ni un ID nuevo para que el usuario pueda aceptarlos; si el precio fluctúa en cada consulta, el trabajo queda atascado. No hay evidencia local de que Higgsfield fluctúe en llamadas consecutivas. **Arreglo propuesto:** guardar la cotización aceptada durante un plazo corto y decidir explícitamente cómo tratar cambios de precio; si se vuelve a cotizar y cambia, devolver el nuevo importe y su `quote_id` al agente sin generar.

4. **Baja. Las páginas que explican el MCP omiten el nuevo requisito obligatorio.** `README.md:65-69` todavía dice que todas las herramientas que gastan créditos se cotizan con `dry_run`, aunque `generate` usa `estimate_cost`, y no menciona `quote_id`. `web/src/app/mcp/page.tsx:18-33` describe `generate` solo como generación con clave de idempotencia y tampoco explica que los lotes y presets necesitan el ID de su cotización. **Arreglo propuesto:** añadir el flujo `estimate_cost → generate(quote_id)` y `dry_run → generate_batch/run_preset(quote_id)`, incluidos `input_video_seconds` y la confirmación excepcional de costo desconocido.

## Comprobaciones satisfactorias

- Los hints por ítem llegan a `quote`: `src/hf_studio/api.py:413-431` mezcla los globales y los del ítem, con prioridad del ítem. `BatchItem.hints`, `BatchIn.hints`, `PresetRun.hints` y `EstimateIn.hints` validan valores positivos y finitos. Las respuestas reales del API mantienen `total` en lotes y `estimate` en presets, claves que usa el MCP.
- `go()` borra `?prompt=` al cambiar de modo o reutilizar; la nota del subtotal ya contempla que la medición del video falle.
- `UV_CACHE_DIR=/tmp/hf-review-uv-cache uv run pytest -q`: **33 passed**. Desde `web/`, `npx tsc --noEmit` y `pnpm lint`: sin errores. `uv run ruff check src tests`: sin errores.

## Veredicto

**CAMBIOS REQUERIDOS**
