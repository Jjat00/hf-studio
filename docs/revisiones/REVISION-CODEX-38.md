# Revisión adversarial de Codex, ronda 38

Fecha: 2026-10-03. HEAD **`4a1e70c`**. Revisión documental de `git show HEAD`: ambos README y AGENTS.md, contrastados con el código y los dos hallazgos de la ronda 37.

**Sin llamadas de generación reales, sin gasto de créditos y sin modificar fuentes ni los documentos revisados.** Las reproducciones usan proveedores simulados, claves falsas y bases temporales. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

**No encontré hallazgos nuevos ni correcciones pendientes en el alcance revisado.**

## Comprobación de las correcciones

| Punto de la ronda 37 | Documentación actual y evidencia | Resultado |
| --- | --- | --- |
| Recotización antes del envío | Ambos README distinguen tablas locales recalculadas antes de cada envío, reutilización de Higgsfield durante 15 minutos y replan inicial automático. Coincide con `worker.refresh_quote`, `worker.replan` y `routing.QUOTE_MAX_AGE`. | Corregido. |
| Cuándo se pide aprobación | Describen precio comprobado superior al techo, desconocido sin permiso para esa opción y retención superior a la autorizada. Coincide con `worker.within_budget`. | Corregido. |
| Desconocido sin techo | Explican que el permiso permite enviar esa opción al precio que acabe teniendo, manteniendo la autorización independiente de retención. Un techo numérico sigue mandando cuando el precio se conoce. | Corregido. |
| Aprobación MCP | README y AGENTS separan la aprobación de la ejecución inicial: `approve_fallback` no recibe `quote_id`; utiliza `max_usd`, `max_reserve_usd` y `accept_unknown_cost`. Coincide con la firma, el cuerpo REST y `api.approve`. | Corregido. |
| Herramientas y conteos | Las dos tablas incluyen `approve_fallback` y `providers_status`. Cada tabla enumera exactamente las 27 herramientas registradas; conteos y badges indican 27. | Corregido. |

Repetí la reproducción del TTL: con cotización Higgsfield reciente, el envío reutiliza el precio guardado; con antigüedad de 901 segundos, consulta `/estimate` y espera aprobación al superar el techo. La descripción nueva refleja ambos resultados.

También comprobé que `cost_usd` y `reserve_usd` son campos reales de la respuesta del trabajo, correspondientes a la opción actual. Al aprobar, la API recotiza y guarda la cotización actual cuando responde 409 por precio, desconocido o retención no autorizados. La aprobación MCP transmite sus importes sin `quote_id`.

Los nombres de claves, comandos y cifras de ejemplo siguen iguales a los comprobados en la ronda 37. El commit no cambia implementación y no altera el veredicto del código multiproveedor de la ronda 36.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q tests/test_routing.py tests/test_mcp_cost.py tests/test_mcp_tools.py`: **102 passed**.
- Reproducción propia del TTL Higgsfield y captura simulada del cuerpo de `approve_fallback`: correctas.
- Comparación por AST de herramientas registradas frente a ambas tablas: **27/27, ninguna ausente**; badges correctos.
- No fue necesario repetir generaciones reales, ffprobe, la suite completa ni comprobaciones de UI para este cambio documental.

## Veredicto

**APROBADO.** Los dos puntos de la ronda 37 están corregidos y la documentación revisada coincide con el código.

**Lista exacta de correcciones pendientes de esta revisión: ninguna.**
