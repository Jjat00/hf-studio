# Revisión adversarial de Codex, ronda 35

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD **`325dbd9`**. Revisados `git show HEAD`, su regresión de ruteo y las protecciones acumuladas del flujo multiproveedor.

Reproducciones sobre una copia de `git archive HEAD` en `/tmp/hf-review35-325dbd9`, con `httpx.MockTransport`, claves falsas, bases y almacenamiento temporales. ffprobe/ffmpeg reales para medios. **Sin generaciones reales, sin gasto de créditos y sin modificar código.** Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: coincidencias genéricas del mensaje siguen permitiendo respaldo tras un error interno de KIE

**Ubicación:** `src/hf_studio/providers/kie.py:33`, `src/hf_studio/providers/kie.py:40`, `src/hf_studio/providers/kie.py:133`, `src/hf_studio/providers/base.py:43`, `src/hf_studio/worker.py:232`.

**Escenario:** el nuevo `PARAM_REJECTION.search(message)` considera suficiente encontrar palabras como `invalid`, `parameter` o `exceed` para convertir un `code:500` en `validation`. Esas palabras también describen fallos internos y respuestas de servicios aguas arriba. Su presencia no identifica un rechazo de los parámetros del usuario ni demuestra que no se haya creado una tarea. `submit_job` conserva esa clasificación; `fallback_safe=True` hace que el worker envíe al siguiente proveedor.

**Reproducción completa:** Seedance 2.0, 720p, 5 s, selección automática y `max_usd=2`. Mantener las tablas de fixtures y cambiar en memoria APIMart a 0,30 USD/s: KIE queda primero por **1,025 USD**, APIMart después por **1,50 USD** y Higgsfield por **1,51 USD**. Registrar el POST KIE y responder HTTP 200 con:

```json
{"code":500,"msg":"Internal server error: invalid response from upstream","data":null}
```

Tras dos ciclos del worker:

```text
initial provider kie
final apimart queued
sent {'higgsfield': 0, 'apimart': 1, 'kie': 1}
KIE error_kind validation, request_id None
fallback_safe True, retryable False
```

El mensaje es **sintético**, elegido para probar el clasificador; no afirmo haberlo observado en producción. La reproducción demuestra dos envíos simulados después de un error interno, no dos cargos reales. Si KIE aceptó la tarea antes de fallar al devolver el resultado, ambos proveedores pueden cobrar. Que el respaldo quepa en el presupuesto no hace seguro repetir una ejecución ambigua.

La clasificación directa confirma otras variantes del mismo defecto:

| Mensaje con `code:500` | Clasificación actual | Permite respaldo |
| --- | --- | --- |
| `resolution is not within the range of allowed options` | `validation` | Sí, control del rechazo conocido. |
| `Internal Server Error` | `ambiguous` | No, reproducción original corregida. |
| `Internal server error: invalid response from upstream` | `validation` | **Sí**. |
| `Internal server error while serializing task parameters` | `validation` | **Sí**. |
| `Internal server error in moderation service` | `moderation` | **Sí**. |

La última variante entra por `MODERATION.search` **antes** de examinar el 500. Mencionar un servicio de moderación que falló tampoco equivale a un rechazo explícito del contenido. Este camino comparte la misma causa: inferir ausencia de ejecución a partir de palabras sueltas.

**Arreglo sugerido:** clasificar los errores internos/desconocidos al enviar como `ambiguous` por defecto. Reservar las excepciones seguras para mensajes completos o patrones estrechos que identifiquen inequívocamente un rechazo de entrada conocido; conservar el mensaje de `resolution` comprobado en vivo. Eliminar las coincidencias genéricas como prueba suficiente y aplicar la misma exigencia a moderación, sin que su regex eluda el tratamiento de 500. Añadir variantes internas con `invalid`, `parameter` y `moderation` a la regresión de ruteo: un POST KIE, cero envíos a los demás y `failed/submission_ambiguous`.

**Origen:** la variante de parámetros es una insuficiencia del cambio de esta ronda. El orden del clasificador de moderación ya existía. La nueva prueba cubre correctamente el error interno simple, pero no los mensajes internos que contienen vocabulario también usado por los rechazos.

## Repetición y regresiones

- **Caso original de la ronda 34:** HTTP 200, `code:500`, `Internal Server Error`: **un POST KIE, cero APIMart/Higgsfield, estado `failed`, clasificación `ambiguous`, sin reintento ni respaldo**. La nueva regresión automática con Higgsfield disponible pasa.
- **Lote con aprobación contradictoria:** `max_total_usd=0.71` y `accept_unknown_cost=true`: **422 `conflicting_approval`, cero trabajos y cero envíos**. Con aceptación falsa, una subida de tarifa conserva el techo y espera aprobación. Con aceptación verdadera y techo ausente, conserva `max_usd=None`.
- **Generación y presets sin techo:** cotización incompleta, tarifa que aparece antes de crear y subida posterior conservan la aceptación de esa opción y el techo explícitamente ausente. El preset transmite la aceptación tras confirmar.
- **Aprobación y desaparición de tarifa:** secuencia 409 → aprobación conocida con aceptación falsa → pérdida de tarifa: **`awaiting_approval`, cero envíos**. Aceptar desconocido con un techo numérico sigue bloqueando un precio conocido superior.
- **Retención:** permanece exigida aunque se acepte un total desconocido. Una retención que sube de 4,9248 a 9,8496 USD devuelve **409 `reserve_not_approved`**; MCP conserva la retención vista.
- **Deduplicación y concurrencia:** proveedores forzados distintos crean trabajos distintos; repetir el mismo recupera el existente; cambiar proveedor con la misma clave devuelve 409. Aprobaciones simultáneas dan 200/409; una cancelación ganadora mantiene `canceled`. La carrera de limpieza de quotes MCP conserva el presupuesto autorizado.
- **Medios:** descarga simultánea sin colisión de temporales. MPD subido devuelve 415. La reproducción con fuente anterior en voz y aislamiento devuelve 422 tras descargar solo el manifiesto; **cero solicitudes al recurso interno del MPD**. ffprobe real lo rechaza por whitelist y un MP4 válido mide 1,0 s.
- **Flujo restante:** revisadas recotización y selección inicial por precio, reservas en respaldo, cuerpos malformados, webhooks, contrato/registro, traducciones y transmisión de aprobación en UI/MCP. No identifiqué otra regresión demostrable. La revisión de UI fue de código y cuerpos de API, sin automatización de navegador.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **331 passed, 2 skipped**.
- Ruff: **All checks passed**.
- `web/`: `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducciones propias con proveedores simulados y tablas de `tests/fixtures/prices_*.json`. No se repitió F0 con créditos reales.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Restringir la clasificación segura de errores KIE a rechazos explícitos comprobados, incluyendo el camino de moderación. Un error interno con vocabulario como `invalid`, `parameter` o `moderation` debe terminar como `ambiguous`, sin reintento ni respaldo. Demostrarlo con la regresión de ruteo automático y conservar como control el rechazo conocido de `resolution`.

La reproducción original de la ronda 34 está corregida. El pendiente es la generalización insegura de sus excepciones.
