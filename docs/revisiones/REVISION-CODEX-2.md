# Revisión adversarial, ronda 2

Fecha: 2026-09-24. Revisados con `git show` los commits `e886b74` y `76172fa`, sus contratos en `src/hf_studio/api.py` y los arreglos de la ronda 1. No se modificó código.

## Hallazgos pendientes o nuevos

1. **Alta. Un agente puede generar sin mostrar antes la cotización al dueño.** `src/hf_studio/mcp_server.py:194-201,249-257` ejecuta un `dry_run` interno y, si el precio está completo, llama de inmediato a la generación. El resultado de ese `dry_run` no se devuelve al agente ni se pide constancia de que el dueño vio y aceptó el importe. Una primera llamada directa a `generate_batch(..., dry_run=False)` o `run_preset(..., dry_run=False)` genera con gasto sin precio visible para el usuario; `tests/test_mcp_cost.py:27-30` incluso verifica este camino. El texto de `web/src/components/use-cases/use-case-panel.tsx:208-210` promete cotización y OK previos. **Arreglo propuesto:** exigir una cotización previa explícita vinculada a los mismos parámetros y una confirmación del importe por el usuario antes de permitir `dry_run=False`; al menos, no presentar el preflight oculto como cumplimiento de la regla de visibilidad. Mantener `confirm_unknown_cost=True` solo para la excepción decidida por el dueño.

2. **Alta. `input_video_seconds` es global y puede dar un total completo pero falso en lotes con videos distintos.** `src/hf_studio/mcp_server.py:182-201` solo admite una duración; `src/hf_studio/api.py:73-76,406-418` pasa el mismo `body.hints` a todos los ítems. Con la fórmula por segundos de entrada de `src/hf_studio/pricing.py:139-151`, dos videos de 5 s y 30 s cotizados con `input_video_seconds=5` dan **$6.81** a $0.681/s y `total.complete: true`, cuando el importe calculado por las duraciones reales sería **$23.835**. El caso “Ad multiplier” reutiliza un mismo anuncio y no dispara este error, pero la herramienta pública acepta ítems con fuentes distintas. **Arreglo propuesto:** aceptar `hints` por ítem y cotizar cada entrada con su duración; si solo se ofrece una duración global, restringirla explícitamente a lotes que compartan el mismo video.

3. **Media. Una duración negativa se acepta como precio completo.** `src/hf_studio/mcp_server.py:164-170` pasa cualquier `float` no nulo; `src/hf_studio/api.py:73-76,96-105` no fija mínimo. `src/hf_studio/pricing.py:143-151` calcula, por ejemplo, **-$2.724** para `input_video_seconds=-4` a $0.681/s, con `missing: []`; `total.complete` resulta verdadero (`src/hf_studio/pricing.py:225-235`) y `_require_price` permite generar. **Arreglo propuesto:** validar duración finita y mayor que cero en MCP y API antes de cotizar; rechazar importes negativos o no finitos como precio incompleto.

4. **Media. `?reuse=` pierde su prioridad si también hay `?prompt=` y el modelo reutilizado es el actual.** `web/src/components/studio/studio.tsx:197-216` anula el prompt solo mientras existe `reuseId`; `reuse()` aplica los valores de la generación y `go()` borra `reuse` pero conserva `prompt` (`:172-193`). Tras la navegación, `promptParam` vuelve a ser el parámetro de URL y sobrescribe el prompt reutilizado. Para un modelo diferente, el resultado depende además del orden de carga del esquema y `pendingValues`, así que la precedencia declarada no es estable. **Arreglo propuesto:** eliminar `prompt` de la URL al reutilizar o conservar la precedencia de `reuse` durante toda esa transición; probar ambos órdenes de carga.

5. **Baja. La nota del subtotal aún promete un precio que puede no llegar.** `web/src/components/use-cases/use-case-panel.tsx:47-53` dice que el estudio mostrará el precio completo al añadir medios. La medición de duración puede fallar o agotarse a los 15 s (`web/src/lib/media.ts:14-32`), y el estudio entonces ofrece la segunda confirmación de costo desconocido. **Arreglo propuesto:** decir que el estudio intentará completar la cotización y, si no puede, pedirá confirmar el costo desconocido.

## Arreglos comprobados

- Los `dry_run` reales entregan `total` para lotes y `estimate` para presets (`src/hf_studio/api.py:406-418,611-617`), las claves que lee `_require_price`. Los hints ya viajan en ambos flujos. Si el precio falta y `confirm_unknown_cost` es falso, el MCP detiene la llamada de generación. La excepción de **Generate anyway** con segunda confirmación en la UI se respeta como decisión del dueño.
- La tarjeta marca subtotal y duración faltante; el tutorial de producto separa los costos y aclara 720p; los límites de referencias y píxeles coinciden con el catálogo. El diálogo ahora mueve, contiene y restaura el foco, y restaura `overflow`.
- `UV_CACHE_DIR=/tmp/hf-review-uv-cache uv run pytest -q`: **32 passed**. Desde `web/`, `npx tsc --noEmit` y `pnpm lint`: sin errores. Estas comprobaciones no ejercitan las carreras de navegación ni prueban visibilidad de precios para el usuario.

## Veredicto

**CAMBIOS REQUERIDOS**
