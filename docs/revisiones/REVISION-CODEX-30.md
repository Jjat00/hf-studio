# Revisión adversarial de Codex, ronda 30

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD `2fc9b65`. Revisados `git show 57cc503 2fc9b65`, el diff contra `461369b` y los flujos de API, MCP, proveedores, worker, medios y UI.

Todas las solicitudes de proveedores se ejecutaron con `httpx.MockTransport`, claves falsas y SQLite/almacenamiento temporales. Para el MPD utilicé un servidor HTTPS en loopback y ffprobe/ffmpeg reales. No hice generaciones reales, no gasté créditos ni modifiqué código. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: aceptar un total desconocido borra una retención conocida y permite aumentarla sin aprobación

**Ubicación:** `src/hf_studio/mcp_server.py:667`, `src/hf_studio/mcp_server.py:698`, `src/hf_studio/api.py:717`, `src/hf_studio/api.py:474`, `src/hf_studio/service.py:142`.

**Escenario:** un lote tiene un video de precio desconocido y una edición Seedance 2.5 de precio y retención conocidos. `total.complete=False` solo describe la falta del costo final completo. Sin embargo, `_authorize` elimina también `reserve_usd`. La API comprueba la retención total únicamente dentro de `if max_total_usd is not None`; al recibir `None`, omite ese control. Finalmente, cada trabajo adopta como reserva aprobada la que encuentre en el plan nuevo. El worker comprueba ese valor recién adoptado y permite el envío. Aceptar un costo final desconocido acaba autorizando una retención distinta de la que se mostró.

**Reproducción:** lote con Seedance 2.0, 720p, 5 s sin tarifa disponible, y Seedance 2.5 video-edit con fuente de 8 s a 720p. El dry-run devuelve:

```json
{"usd":2.0736,"credits":null,"complete":false,"reserve_usd":4.9248}
```

Emitir el quote y ejecutar el propio `generate_batch(..., confirm_unknown_cost=True)` produce `max_total_usd=None` **y `max_total_reserve_usd=None`**. Antes de entregar ese cuerpo a la API, duplicar `seedance-2.5|720P-input` en la tabla local. El POST del lote responde **202**; el trabajo APIMart guarda **4,1472 USD de precio y 9,8496 USD de reserva aprobada**, y `worker.submit` hace **un POST simulado a APIMart**. No aparece `reserve_not_approved` ni `awaiting_approval`, pese a que se mostraron 4,9248 USD de retención.

**Arreglo sugerido:** separar la autorización de costo final de la autorización de retención. Conservar la retención conocida aunque el precio total esté incompleto; distinguir además reserva conocida de reserva incompleta. Validar `max_reserve_usd` y `max_total_reserve_usd` independientemente de que exista un techo de costo final, en generación, presets y lotes. No convertir la reserva actual de una nueva cotización en consentimiento cuando falta la autorización. Una retención nueva o mayor debe detener el envío y pedir aprobación.

### 2. MEDIA: `confirm_unknown_cost=True` en APIMart/KIE se convierte en una aprobación imposible

**Ubicación:** `src/hf_studio/worker.py:285`, `src/hf_studio/worker.py:311`, `src/hf_studio/worker.py:326`, `src/hf_studio/api.py:795`.

**Escenario:** el MCP permite confirmar explícitamente un costo desconocido. La recotización obligatoria de los proveedores con tabla local vuelve a obtener un precio desconocido y `within_budget` siempre lo rechaza. El trabajo pasa a `awaiting_approval`, pero `/approve` solo admite un precio conocido y vuelve a rechazarlo. La autorización explícita se pierde porque el Job no distingue «desconocido aceptado para esta ejecución» de «sin autorización».

**Reproducción:** vaciar la tabla APIMart en el entorno falso, cotizar Seedance 2.0 con `provider="apimart"`, emitir un quote válido y llamar al propio `generate(..., confirm_unknown_cost=True)`. La API acepta el cuerpo con **202**. Al ejecutar `worker.submit`, el estado queda en **`awaiting_approval`, `cost_usd=None`, cero envíos**. Aprobar incluso con `max_usd=100` devuelve **409 `cost_unknown`**. El precio sigue siendo el mismo desconocido que se aceptó; no ocurrió un aumento ni un respaldo. La misma condición afecta a KIE por `has_price_table=True`.

**Arreglo sugerido:** persistir una autorización explícita de costo desconocido ligada a la ejecución y opción inicialmente aceptadas, y respetarla al recotizar esa opción. No extenderla automáticamente a otros proveedores ni a retenciones nuevas. Si se decide eliminar esa modalidad, rechazarla antes de crear trabajos y actualizar el contrato MCP/UI; el estado actual promete una operación que no puede continuar.

### 3. MEDIA: las descargas concurrentes del mismo medio comparten y borran el temporal

**Ubicación:** `src/hf_studio/media.py:73`, `src/hf_studio/media.py:75`, `src/hf_studio/media.py:79`, `src/hf_studio/media.py:84`.

**Escenario:** dos estimaciones de voz/aislamiento o dos procesamientos con conservación de audio descargan la misma URL cuando todavía no está en caché. Ambas abren el mismo `<hash>.part` con `wb`. Una lo renombra o borra mientras la otra todavía lo utiliza. Además de interferir en los bytes escritos, la segunda puede fallar al leerlo o renombrarlo. `cached_source` no captura ese error y las rutas de estimación pueden devolver 500.

**Reproducción:** iniciar dos `cached_source` con idéntica URL y almacenamiento temporal, usando dos streams HTTP falsos detenidos por eventos hasta que ambos tengan el archivo abierto. Liberar ambos con bytes que cumplen la firma MP4. `asyncio.gather(..., return_exceptions=True)` devuelve **una ruta válida y un `FileNotFoundError`**. No hace falta un archivo malicioso ni una URL ajena: basta la concurrencia normal sobre una fuente propia.

**Arreglo sugerido:** utilizar un temporal distinto por descarga, validarlo y publicar el resultado mediante reemplazo atómico. El `finally` debe borrar únicamente el temporal de su descarga. Un lock por URL puede evitar trabajo duplicado dentro del proceso, pero no debe ser la única protección si pueden existir varios procesos. Verificar dos descargas simultáneas y el caso donde una falla mientras la otra termina correctamente.

### 4. MEDIA: recotizar solo la opción actual puede enviar por un proveedor que ya no es el más barato

**Ubicación:** `src/hf_studio/worker.py:305`, `src/hf_studio/worker.py:314`, `src/hf_studio/worker.py:324`, `src/hf_studio/worker.py:326`.

**Escenario:** el plan se ordenó antes de cambiar una tabla local. Ahora se actualiza el precio de su primera opción, pero no se reconsidera el orden. Si la tarifa nueva cabe en el presupuesto aprobado, el worker envía aunque otra opción del mismo modelo tenga un precio menor. Se respeta el techo, pero se incumple el objetivo de usar el proveedor más barato.

**Reproducción:** crear Seedance 2.0, 720p, 5 s en selección automática, con `max_usd=2`. El plan inicial elige APIMart por **0,71 USD**, seguido de KIE por **1,025 USD**. Cambiar `seedance-2.0|720P` a 0,30 USD/s antes del envío. Un `/v1/estimate` nuevo elige **KIE por 1,025 USD**. `worker.submit` recotiza APIMart a **1,50 USD** y hace **un POST simulado a APIMart, cero a KIE**. La tabla nueva ya estaba disponible en la aplicación.

**Arreglo sugerido:** antes del primer envío automático, reconsiderar las opciones elegibles del mismo modelo con las tarifas vigentes y seleccionar la más barata que satisfaga costo y retención aprobados. Conservar la elección explícita cuando el usuario forzó un proveedor. No reactivar opciones ya enviadas o ambiguas al reordenar respaldos; si ninguna opción admisible cabe en lo aprobado, pedir aprobación sobre la alternativa más barata actual.

## Repetición de los ocho casos de la ronda 29

| Caso | Resultado en estos commits |
| --- | --- |
| 503 genérico | Higgsfield, APIMart y KIE: `ambiguous`, sin reintento ni respaldo. En worker APIMart: un envío, cero KIE, `failed/submission_ambiguous`. |
| Cambio de tabla dentro del TTL | Con techo de 0,71 USD y nueva tarifa APIMart de 1,50 USD: cero envíos, espera aprobación. La protección del techo funciona; el orden de proveedores tiene el hallazgo 4. |
| Retención en respaldo | El plan, la recotización y la generación conservan 4,9248 USD y `kind=approx`. El respaldo con reserva no aprobada espera; `/approve` sin reserva devuelve 409 y con reserva aprobada devuelve 200. Excepción pendiente: hallazgo 1. |
| UI tras 409 | Aprobar KIE a 1,025 USD cuando ya cuesta 2,50 responde 409. El GET siguiente publica 2,50 y aprobar ese importe responde 200. La tarjeta usa el precio del plan actualizado, muestra `~` y la retención, y los consumidores mantienen polling. Verificación de código y API, sin automatización de navegador. |
| Cuerpos malformados | En los tres adaptadores, texto no JSON, lista/cuerpo inesperado e ID ausente producen `ambiguous`, `retryable=False`, `fallback_safe=False`. El worker con `data:["broken"]` termina `failed/submission_ambiguous`, con un envío y sin quedar `submitting`. |
| MPD anterior en voz/aislamiento | Ambos endpoints gratuitos responden 422 después de un único GET del archivo fuente; **ningún GET de `/internal.mp4`**. ffprobe real sobre el MPD local lo rechaza por whitelist; un MP4 real válido mide 1,0 s. La subida MPD nueva devuelve 415. `guarded()` aplica restricciones antes de cada `-i` en los comandos revisados. |
| Carrera de quotes MCP | Canjear antes de expirar, pausar 20 ms y emitir otro quote que limpia el anterior ya no pierde el precio: `generate` conserva **`max_usd=0.71`**. Dos aprobaciones concurrentes producen 200/409; cancelación que gana produce aprobación 409 y conserva `canceled`. Un resultado de sondeo obsoleto pierde el CAS y no causa un segundo envío KIE. |
| Lote de total desconocido | El MCP envía `max_total_usd=None`, ya no el subtotal. La API acepta el lote de la reproducción. La eliminación conjunta de la retención produce el hallazgo 1; el consentimiento desconocido con tabla local tiene el hallazgo 2. |

También repetí el rechazo de aumentos en lotes/presets, el rechazo de precio desconocido bajo techo numérico y la traducción de seed/bitrate explícitos sin equivalente. KIE sigue sin rutas Seedance edit/extend. No encontré nuevas fugas de claves ni un bypass de las restricciones de ffprobe en las rutas revisadas.

## Validación

- `uv run pytest -q`: **315 passed, 2 skipped**. Se usó `UV_CACHE_DIR=/tmp/hf-review28-uv` por las restricciones del entorno.
- `uv run ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducciones independientes con eventos para carreras, transportes falsos, tablas de `tests/fixtures/prices_*.json` y medios reales locales. Las mutaciones de precios, métodos y fechas se limitaron a objetos/BD temporales de esas reproducciones.

La decisión de comparar `max_usd` con el costo final estimado y aprobar la retención por separado es aceptable. Estos commits implementan esa separación para precios completos y respaldos ordinarios. El hallazgo 1 demuestra que todavía no se cumple cuando se acepta un total desconocido. La reserva consentida no equivale a autorizar que aumente el costo final por encima de su propio techo.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Conservar y exigir la autorización independiente de retención cuando el costo final es desconocido, y detener una retención nueva o mayor antes de crear/enviar trabajos, también en lotes y presets.
2. Resolver el contrato de costo desconocido explícitamente aceptado: persistir y respetar esa autorización para la opción inicial, o rechazar esa modalidad antes de encolar en lugar de dejar una aprobación imposible.
3. Aislar los temporales de descargas simultáneas y evitar que una descarga borre o sobrescriba el archivo de otra.
4. Reconsiderar el proveedor más barato cuando cambian tarifas antes del envío automático, respetando los techos, la elección forzada y las restricciones contra reenvíos ambiguos.
