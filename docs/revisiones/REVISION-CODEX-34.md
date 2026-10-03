# Revisión adversarial de Codex, ronda 34

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD **`a82f328`**. Revisados `git show HEAD`, la corrección de lotes y el flujo multiproveedor acumulado: autorización, cotizaciones, precios, envíos, respaldos, deduplicación, webhooks, MCP, UI y medios. Reproducciones propias sobre una copia de `git archive a82f328` en `/tmp/hf-review34-a82f328`.

Los proveedores se simularon con `httpx.MockTransport`, claves falsas y bases/almacenamiento temporales. Utilicé ffprobe/ffmpeg reales y HTTPS en loopback para medios, y consulté documentación pública de KIE en solo lectura. No hice generaciones reales, no gasté créditos y no modifiqué código. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: KIE permite respaldo después de un error interno con HTTP 200 y `code:500`

**Ubicación:** `src/hf_studio/providers/kie.py:42`, `src/hf_studio/providers/kie.py:119`, `src/hf_studio/providers/base.py:45`, `src/hf_studio/worker.py:239`.

**Escenario:** KIE comunica sus errores mediante el campo JSON `code`, habitualmente bajo HTTP 200. `_kind` convierte **cualquier `code:500` en `validation`**, independientemente de su mensaje. Por eso un error interno genérico no entra en la conversión a `ambiguous` de `submit_job`. El worker lo interpreta como un rechazo seguro sin cobro y envía al proveedor siguiente.

El comentario del código y el test existente recogen una respuesta 500 de parámetros inválidos. Eso demuestra que algunos errores de validación usan ese código, pero no demuestra que todos lo sean. La documentación pública del endpoint `/api/v1/jobs/createTask` distingue el código 422 de validación y el 500 de error interno; no establece que un error interno garantice ausencia de tarea o cobro. [Documentación oficial de KIE para createTask](https://docs.kie.ai/cn/market/kling/v2-5-turbo-image-to-video-pro).

**Reproducción:** Seedance 2.0, 720p, 5 s, selección automática y `max_usd=2`. Ajustar la tarifa APIMart a 0,30 USD/s para que el plan inicial sea KIE **1,025 USD**, APIMart **1,50 USD**, Higgsfield **1,51 USD**. El transporte KIE registra el POST y responde:

```json
{"code":500,"msg":"Internal Server Error","data":null}
```

con **HTTP 200**. Tras dos ciclos del worker, el resultado es **un POST a KIE y otro a APIMart**, estado final **`queued` en APIMart**. El historial registra el fallo KIE como **`validation`**, sin request ID. La llamada directa al adaptador confirma **`fallback_safe=True`**, aunque el mensaje no contiene ningún rechazo de parámetros.

No demostré un doble cargo real: todos los envíos fueron simulados. Sí demostré que la aplicación envía por segunda vez después de una respuesta interna ambigua que no permite asegurar si KIE creó o cobró la primera tarea. Si esa primera tarea fue aceptada antes del error, los dos proveedores pueden cobrar. Esta es la misma condición que las correcciones anteriores bloquean para errores HTTP genéricos, pero dentro del sobre JSON de KIE.

**Arreglo sugerido:** tratar un `code:500` genérico al enviar como error interno ambiguo, sin reintento ni respaldo. Conservar la clasificación de validación únicamente para rechazos explícitos de parámetros cuya ausencia de ejecución esté establecida; no generalizar desde una respuesta de validación observada a todo el código 500. Añadir una prueba con el cuerpo anterior y verificar un solo POST KIE, cero envíos a otros proveedores y `failed/submission_ambiguous`.

**Origen:** defecto previo a `a82f328`, detectado al revisar el flujo completo y contrastar la clasificación con la documentación. La corrección de lotes del último commit funciona; este hallazgo no procede de ella. Las reproducciones anteriores de HTTP 503 y cuerpos malformados no cubrían esta variante de HTTP 200 con error interno estructurado.

## Repetición del hallazgo de la ronda 33

| Petición del lote | Resultado |
| --- | --- |
| `max_total_usd=0.71`, `accept_unknown_cost=true` | **422 `conflicting_approval`, cero Jobs y cero envíos**. |
| La misma combinación con techo cero | **422**, cero Jobs y cero envíos; no hay bypass por valor falsy. |
| Dos copias, techo 1,42 USD y aceptación verdadera | **422**, cero Jobs y cero envíos; no hay creación parcial. |
| Techo 0,71 USD, aceptación falsa, tarifa sube antes de enviar | Conserva el presupuesto y queda **`awaiting_approval`, cero envíos**. |
| Total ausente y aceptación verdadera, tarifa sube a 1,50 USD | Mantiene la modalidad sin techo y envía una vez a la opción aceptada. |

También ejecuté el propio `generate_batch` del MCP con cotizaciones completas e incompletas. Con total completo transmite **techo numérico y aceptación falsa**; con total incompleto aceptado transmite **techo `None` y aceptación verdadera**. No genera la combinación que ahora rechaza REST.

## Comprobaciones del flujo acumulado

- **Generación y aprobación con techo:** precio inicialmente desconocido y techo 0,71 USD; al reaparecer APIMart a 1,50 o KIE a 2,50, el worker espera aprobación y no envía. La combinación sigue funcionando por trabajo.
- **Permisos tras 409:** la secuencia rechazo → aprobación conocida con aceptación falsa → desaparición de tarifa conserva el permiso falso y termina `awaiting_approval`, cero KIE.
- **Sin techo explícito:** cotización desconocida, tarifa que reaparece antes de crear y aumento posterior mantienen `max_usd=None` y el permiso para esa opción, tanto en generación como en preset.
- **Alcance del permiso:** aceptar una opción desconocida no autoriza un respaldo desconocido distinto; el respaldo vuelve a esperar aprobación.
- **Retenciones:** aceptar un total desconocido no elimina su reserva aprobada. Una subida de 4,9248 a 9,8496 USD devuelve 409 `reserve_not_approved`, sin envío. El plan y la UI conservan la reserva y la naturaleza aproximada del precio.
- **Proveedor más barato:** APIMart sube de 0,71 a 1,50 con techo 2 USD; el replan elige KIE por 1,025. Forzar APIMart conserva esa elección.
- **Deduplicación:** proveedores forzados distintos crean Jobs distintos; repetir el mismo forzado o selección automática devuelve el existente. Cambiar proveedor con una misma clave de idempotencia devuelve 409.
- **Ambigüedad cubierta:** HTTP 503, respuesta sin ID, texto no JSON y listas malformadas siguen sin reintento ni respaldo en los tres adaptadores. El fallo pendiente es el error interno JSON de KIE descrito arriba.
- **Carreras:** aprobaciones concurrentes producen 200/409; cancelación que gana conserva `canceled`. El resultado de sondeo obsoleto pierde el CAS y no duplica respaldo. La limpieza concurrente de quotes mantiene el techo MCP de 0,71 USD.
- **Webhooks:** comprobados token, proveedor y correlación Higgsfield; el payload dispara una consulta autenticada de estado y no decide el resultado de la generación.
- **Medios:** temporales concurrentes sin colisión. Subida MPD nueva: 415. Voz y aislamiento con una subida anterior: solo GET del manifiesto fuente, 422, ningún GET interno. ffprobe real rechaza DASH por whitelist; MP4 válido mide 1,0 s.
- **MCP y UI:** cotización y aceptación se transmiten en generación, presets y aprobación; la tarjeta muestra la cotización actual tras 409, retención y aceptación explícita de desconocido. Inspección de código y reproducción de cuerpos de API, sin automatización de navegador.
- **Mapas y contrato:** seed/bitrate explícitos sin equivalente siguen como `unsupported`; KIE mantiene retiradas Seedance edit/extend. Higgsfield sigue gestionando las subidas de medios y el registro conserva el contrato común de proveedores.

No encontré otra regresión nueva de autorización, deduplicación, SSRF o exposición de claves en lo revisado.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **327 passed, 2 skipped**.
- `uv run ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducciones independientes con la copia exacta de `a82f328`, tablas de `tests/fixtures/prices_*.json`, bases temporales y transportes simulados. No se repitió la prueba F0 con créditos reales ni se editaron fuentes del repositorio.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Clasificar el error interno genérico de KIE con HTTP 200 y `code:500` como `ambiguous`, y demostrar que termina sin reintento ni respaldo: un solo POST al proveedor inicial y cero a los demás. No inferir rechazo seguro de parámetros únicamente del número 500.

El hallazgo de la ronda 33 está corregido y no quedan pendientes de esa corrección.
