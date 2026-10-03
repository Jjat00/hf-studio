# Revisión adversarial de Codex, ronda 31

Fecha: 2026-10-03. Versión revisada: **`5989735`**, comparada con `2fc9b65` mediante `git show` y diff. Durante la revisión aparecieron cambios ajenos en API, servicio y tests, que posteriormente quedaron en `c9ae337`. No los modifiqué ni los incluyo en este veredicto. Para evitar mezclar versiones, repetí las pruebas y reproducciones sobre una copia de `git archive 5989735` en `/tmp/hf-review31-5989735`.

Usé proveedores simulados con `httpx.MockTransport`, claves falsas, SQLite y almacenamiento temporales. Las pruebas de medios utilizaron ffprobe/ffmpeg reales y un servidor HTTPS en loopback. No ejecuté generaciones reales ni gasté créditos. Solo añadí este informe; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: `unknown_accepted` ignora incluso un techo numérico explícito y persistido

**Ubicación:** `src/hf_studio/worker.py:286`, `src/hf_studio/api.py:496`, `src/hf_studio/api.py:509`, `src/hf_studio/api.py:827`, `src/hf_studio/api.py:860`.

**Escenario:** aceptar un costo desconocido sin techo puede autorizar que posteriormente aparezca un precio conocido para esa misma opción. El problema es que la API también permite combinar esa aceptación con un `max_usd` numérico: lo guarda como presupuesto aprobado, pero el worker lo ignora por el `or unknown_accepted`. La misma petición se rechazaría si ese precio ya fuera conocido al entrar en la API. El resultado depende del momento en que reaparece la tarifa, en lugar de respetar el techo que el cliente envió.

**Reproducción inicial:** vaciar la tabla APIMart y crear Seedance 2.0, 720p, 5 s con `provider="apimart"`, `max_usd=0.71` y `accept_unknown_cost=true`. La API devuelve **202** y conserva `max_usd=0.71`. Restaurar la tabla con `seedance-2.0|720P=0.30` antes de enviar. El worker recotiza a **1,50 USD**, hace **un POST simulado a APIMart** y deja el trabajo `queued`, todavía publicando **`max_usd=0.71`**. Si 1,50 hubiera estado disponible al crear, `authorize` habría devuelto `cost_changed` con esos mismos argumentos.

**Reproducción en respaldo:** crear la misma generación con techo de 0,71 USD; APIMart falla sin cobrar y KIE queda esperando aprobación. Quitar temporalmente la tarifa KIE y llamar a `/approve` con `max_usd=0.71` y `accept_unknown_cost=true`: **200**, presupuesto persistido **0,71**. Restaurar KIE a 0,50 USD/s y enviar: **un POST simulado a KIE por 2,50 USD**, estado `queued`, techo publicado **0,71**. La aceptación de desconocido no se propagó a otro proveedor; el fallo consiste en ignorar el límite dentro de la opción aceptada.

**Arreglo sugerido:** definir de forma inequívoca si la autorización es sin techo o tiene techo. Si existe un `max_usd` explícito, una tarifa conocida superior debe detenerse antes del POST; el flag no debe anularlo silenciosamente. Si aceptar un desconocido significa autorizar sin límite, exigir esa modalidad explícita, rechazar la combinación contradictoria o quitar el techo mediante una acción de aprobación que lo comunique claramente. Mantener el límite de reserva independiente. Verificar tanto creación como aprobación cuando la tarifa pasa de desconocida a conocida. Aceptar cambios dentro de una autorización sin techo es compatible con la decisión de producto; publicar un techo finito y sobrepasarlo no lo es.

### 2. MEDIA: confirmar un precio desconocido desde un preset no envía `accept_unknown_cost`

**Ubicación:** `web/src/components/presets/preset-runner.tsx:86`, `web/src/components/presets/preset-runner.tsx:96`, `web/src/lib/studio.ts:167`, `web/src/lib/studio.ts:177`, `src/hf_studio/worker.py:315`.

**Escenario:** el formulario de presets conserva su confirmación en dos pasos para costo incompleto, pero `studio.runPreset` no acepta ni envía el nuevo flag. La corrección se conectó al estudio general y al MCP, pero no a este formulario. Con todas las opciones sin precio, la API crea un trabajo sin `unknown_accepted`; el replan no encuentra ninguna opción dentro del presupuesto y lo manda a `awaiting_approval`. La tarjeta deshabilita aprobar cuando `usd` es desconocido, aunque el usuario ya lo había confirmado en el formulario.

**Reproducción:** en el entorno falso, vaciar ambas tablas locales y hacer que la estimación Higgsfield devuelva precio desconocido. Crear un preset Seedance 2.0 con entrada válida. Su dry-run devuelve `estimate.usd=None`. Enviar el cuerpo que construye la UI después de la confirmación, `{"variables":{}}`, devuelve **202**. `worker.submit` deja **`awaiting_approval`, cero envíos**. La inspección del formulario confirma que su segunda pulsación no añade el flag; no automaticé el navegador.

**Arreglo sugerido:** pasar la aceptación explícita desde `PresetRunner` a `studio.runPreset` y enviarla en la petición, igual que en el estudio general. Ligarlo a la vista previa confirmada, conservar la retención aprobada y reenviar los mismos datos de cotización. No activarlo al primer clic ni por el simple hecho de que falle la estimación. Verificar que un preset confirmado con precio desconocido se envíe una vez y no se quede esperando una segunda aprobación imposible.

### 3. MEDIA: el MCP no puede aprobar el costo desconocido de un respaldo

**Ubicación:** `src/hf_studio/mcp_server.py:510`, `src/hf_studio/mcp_server.py:517`, `src/hf_studio/api.py:827`.

**Escenario:** REST ahora permite aprobar explícitamente una opción desconocida, pero la única herramienta MCP de aprobación sigue teniendo únicamente `generation_id`, `max_usd` y `max_reserve_usd`. No hay parámetro ni campo enviado para aceptar el desconocido. Un agente que opera mediante el MCP no puede utilizar la nueva capacidad para continuar el mismo trabajo después de obtener el consentimiento del usuario.

**Reproducción:** APIMart rechaza el envío por saldo y la generación queda esperando KIE. Quitar su tarifa local. El cuerpo que puede construir `approve_fallback`, con `max_usd=1.025`, devuelve **409 `cost_unknown`**. La firma de la herramienta carece del parámetro de aceptación. El mismo endpoint con `accept_unknown_cost=true` añadido manualmente responde **200** y el worker hace **un POST simulado a KIE**, quedando `queued`. Esto confirma una diferencia real entre las capacidades REST y MCP, no una indisponibilidad del proveedor.

**Arreglo sugerido:** exponer una aceptación explícita de precio desconocido en `approve_fallback`, enviarla a REST y documentar que solo se usa después del consentimiento del usuario. Mantener la aprobación independiente de retención y resolver con el hallazgo 1 cómo expresar una autorización sin techo. Cubrir un respaldo que pierde su tarifa después de entrar en `awaiting_approval`.

## Repetición de los cuatro hallazgos de la ronda 30

| Caso | Resultado en `5989735` |
| --- | --- |
| Total desconocido y retención conocida | El dry-run mixto devuelve costo parcial 2,0736 USD y retención 4,9248 USD. El propio MCP conserva **`max_total_reserve_usd=4.9248`** y acepta el total desconocido. Tras duplicar la tarifa de entrada, el lote devuelve **409 `reserve_not_approved`**, sin enviar trabajos. Una generación con precio sin techo pero `max_reserve_usd=0` también devuelve 409. |
| Desconocido aceptado en APIMart | Quote incompleto y `generate(..., confirm_unknown_cost=True)` transmiten la aceptación. La generación queda **`queued` con un envío simulado**, sin la aprobación imposible anterior. El flag sigue limitado a su opción; un respaldo desconocido distinto vuelve a esperar aprobación. Las combinaciones pendientes se describen en los hallazgos 1 a 3. |
| Caché concurrente | Dos descargas detenidas por eventos hasta que ambas tienen el temporal abierto terminan con **dos rutas válidas**, sin `FileNotFoundError`. El test añadido verifica contenido y ausencia de `.part` residuales. |
| Proveedor más barato antes del envío | APIMart pasa de 0,71 a 1,50 USD con techo de 2 USD. El replan elige **KIE por 1,025 USD**, un envío KIE y cero APIMart. Con `provider="apimart"` explícito, conserva APIMart, como corresponde. |

## Comprobaciones de regresión adicionales

- **503 y cuerpos malformados:** los tres adaptadores conservan clasificación `ambiguous`, sin reintento ni respaldo. En el worker, 503 y `data:["broken"]` de APIMart terminan `failed/submission_ambiguous`, con un envío y cero KIE.
- **Precios y aprobación:** aumentos de lote/preset y precio desconocido bajo techo sin aceptación siguen devolviendo 409. El cambio de tabla dentro del TTL no se envía por encima del techo ordinario. Un `/approve` rechazado publica la tarifa actual de KIE, 2,50 USD.
- **Carreras:** dos aprobaciones concurrentes producen 200/409; cancelación que gana mantiene `canceled` y aprobación 409. Un resultado de sondeo obsoleto pierde el CAS y no duplica el envío de respaldo. La limpieza concurrente de quotes conserva `max_usd=0.71` en el MCP.
- **MPD y ffprobe real:** la subida nueva devuelve 415. Los endpoints gratuitos de voz y aislamiento sobre un Upload anterior hacen solo GET del MPD fuente y responden 422; no solicitan `/internal.mp4`. ffprobe local rechaza el demuxer DASH por whitelist; un MP4 válido mide 1,0 s.
- **Traducciones:** seed/bitrate explícitos sin equivalente siguen como `unsupported`; KIE continúa sin Seedance edit/extend. No encontré una nueva fuga de claves o bypass de ffprobe en las rutas revisadas.

## Validación

- Suite completa sobre la copia exacta de `5989735`: **319 passed, 2 skipped** (`pytest -q`, intérprete de la venv del proyecto y `PYTHONPATH` de la copia).
- `ruff check src tests` sobre esa copia: **All checks passed**.
- `pnpm lint` y `pnpm exec tsc --noEmit --incremental false` en `web/`: **correctos**. Las fuentes web no cambiaron respecto a `5989735` durante la revisión.
- Reproducciones propias con tablas de `tests/fixtures/prices_*.json`, transportes falsos y bases temporales. Los cambios de tarifas, fechas y métodos se limitaron a esos entornos. Los cambios ajenos del workspace se dejaron intactos.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Evitar que `unknown_accepted` anule silenciosamente un `max_usd` finito: respetarlo cuando aparece una tarifa conocida, o expresar y validar de forma explícita una autorización sin techo, tanto al crear como al aprobar.
2. Enviar la aceptación de precio desconocido confirmada desde el formulario de presets de la UI hasta REST, conservando los datos y la retención aprobados.
3. Permitir la aprobación explícita de un respaldo de precio desconocido mediante `approve_fallback` del MCP, con consentimiento y retención independiente.
