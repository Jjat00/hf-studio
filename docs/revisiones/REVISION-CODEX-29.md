# Revisión adversarial 29: correcciones de multiproveedor

Fecha: 2026-10-03. HEAD y commit revisado: `461369b75e01ebd3cb71e680b9159385b2e48188`, sobre `b3cb108`. Revisé `git show 461369b`, repetí las reproducciones de la ronda 28 y recorrí autorización de precio, envío, respaldo, aprobación, cancelación, medición de medios y UI/MCP.

No modifiqué código ni hice llamadas reales que generaran o gastaran créditos. Las pruebas de generación usan ASGI, SQLite temporal, `httpx.MockTransport` y las tablas reales aportadas en `tests/fixtures`. Para medios usé ffprobe/ffmpeg reales y un servidor HTTPS temporal en loopback, sin intervenir servidores del producto. No leí `.env`. Conservé `tt.png` y el informe de la ronda 28.

## Hallazgos

### 1. ALTA: el 503 genérico sigue permitiendo reintentos y respaldo con posible doble cobro

**Ubicación:** `src/hf_studio/providers/apimart.py:121`, `src/hf_studio/higgsfield.py:120`, clasificación en `src/hf_studio/providers/base.py:210` y `src/hf_studio/higgsfield.py:63`.

**Escenario:** el backend acepta la tarea, pero un intermediario devuelve HTTP 503 con texto `Service Unavailable`. APIMart e Higgsfield lo clasifican como `unavailable`, no como `server`; por ello no entra en la nueva conversión a `ambiguous`. Sigue siendo `retryable` y `fallback_safe`. Un 503 genérico no demuestra que el proveedor haya rechazado la petición antes de crear la tarea.

**Reproducción:** los dos adaptadores devuelven `unavailable`, `retryable=True`, `fallback_safe=True` para esa respuesta. Con APIMart falso devolviendo 503 y un Job con `max_usd=2`, tres ciclos producen **dos POST a APIMart y uno a KIE**. Si los 503 llegaron después de aceptar, se repite un gasto no reembolsado. KIE sí trata ese HTTP 503 como ambiguo.

**Arreglo sugerido:** convertir también el 503 genérico en ambiguo. Solo admitir reintento/respaldo para un rechazo explícito identificable del proveedor que garantice ausencia de tarea/cobro, no por el código HTTP o un comentario del adaptador. Añadir este caso a los tests, junto al 502 ya cubierto.

### 2. ALTA: cambiar la tabla dentro de los 15 minutos permite enviar por encima de `max_usd`

**Ubicación:** `src/hf_studio/worker.py:292`, `src/hf_studio/routing.py:225`.

**Escenario:** un Job se crea con una cotización de 0,71 USD. La tabla sincronizada cambia antes del envío, pero aún no pasaron 15 minutos. `refresh_quote` retorna inmediatamente y el worker envía el precio antiguo. El límite de antigüedad solo detecta el paso del tiempo; no detecta un cambio de tarifa que la aplicación ya conoce. Los revendedores no reciben un quote remoto que les obligue a respetar el precio guardado.

**Reproducción:** crear Seedance 2.0, 720p, 5 s, forzando APIMart y `max_usd=0.71`; cambiar `seedance-2.0|720P` a 0,30 USD/s. `/v1/estimate` devuelve **1,50 USD**, pero `worker.submit` hace **un POST a APIMart**, sin `awaiting_approval`, porque `quoted_at` es reciente. El caso de más de 15 minutos sí se bloquea correctamente.

**Arreglo sugerido:** invalidar la cotización al cambiar la versión de su tabla y contrastar la tarifa vigente antes del envío, incluso dentro del TTL. Revalidar también las opciones de respaldo. Guardar la versión de precios en el plan; 15 minutos pueden limitar consultas externas, pero no justificar ignorar una tarifa local ya actualizada. Si supera el techo, volver a aprobación.

### 3. ALTA: la reserva se pierde al guardar el plan y no se muestra al aprobar un respaldo

**Ubicación:** `src/hf_studio/routing.py:90`, `src/hf_studio/routing.py:237`, `src/hf_studio/api.py:335`, `web/src/components/generations/generation-card.tsx:280`.

**Escenario:** `/estimate` incluye `reserve_usd`, pero `Plan.stored` lo descarta; `requote` tampoco lo incorpora y `job_out` publica únicamente proveedor y USD en cada opción. Tras fallar el primer proveedor, ni el agente que consulta la generación ni el panel de aprobación reciben la reserva del proveedor siguiente. El panel muestra únicamente el precio final estimado, sin la reserva ni la clasificación `approx`.

**Reproducción:** edición Seedance 2.5 con fuente de 8 s a 720p. La cotización APIMart contiene **2,0736 USD estimados y 4,9248 USD de reserva**, pero el plan persistido tiene `reserve_usd=None` por ausencia del campo. Con Higgsfield falso cotizado a 0,10 USD como primera opción, su fallo deja APIMart en `awaiting_approval`; la respuesta solo muestra 2,0736 USD. Aprobar con `max_usd=2.0736` devuelve **200** sin informar de la retención de 4,9248 USD. El aviso de `INSTRUCTIONS` no puede recuperar un dato que la generación no devuelve.

**Arreglo sugerido:** conservar y publicar reserva, naturaleza aproximada y su vigencia en el plan, la recotización y la generación. Mostrar esas cantidades antes de aprobar un respaldo en UI y MCP. Conservar qué reserva fue consentida; una reserva nueva o mayor que la autorizada debe pedir aprobación aunque la estimación final esté dentro de `max_usd`.

### 4. MEDIA: después de `cost_changed`, la UI vuelve a aprobar eternamente el importe anterior

**Ubicación:** `src/hf_studio/api.py:750`, `web/src/components/generations/generation-card.tsx:287`, `web/src/components/generations/generation-card.tsx:302`.

**Escenario:** el respaldo esperaba aprobación por 1,025 USD, pero ahora cuesta 2,50 USD. La API recotiza y rechaza correctamente. Sin embargo, lanza el error antes de actualizar el plan; la tarjeta solo guarda el mensaje de error y su botón continúa enviando el precio de `g.plan`. El polling sigue recibiendo el importe anterior. No existe una acción en esa tarjeta para adoptar la nueva cotización y aprobarla.

**Reproducción:** actualizar la fila de KIE y llamar dos veces a `/approve` con el precio que devuelve `/generations/{id}`. Ambas llamadas responden **409 con 2,50 USD**, mientras los dos GET siguen indicando **1,025 USD**. El botón de la UI siempre manda 1,025. Un cliente que construye manualmente una petición con 2,50 puede continuar; la UI no ofrece ese flujo.

**Arreglo sugerido:** guardar mediante CAS la cotización nueva manteniendo `awaiting_approval`, o devolver una cotización estructurada que la UI pueda mostrar y usar tras otra acción explícita del usuario. Actualizar el botón y la advertencia sin aprobar automáticamente el precio nuevo. Cubrir además la recuperación desde un precio inicialmente desconocido.

### 5. MEDIA: algunas respuestas ilegibles aún escapan del adaptador y dejan `submitting` indefinidamente

**Ubicación:** `src/hf_studio/higgsfield.py:118`, `src/hf_studio/higgsfield.py:159`, `src/hf_studio/providers/apimart.py:130`, `src/hf_studio/providers/kie.py:124`, `src/hf_studio/worker.py:153`, `src/hf_studio/worker.py:419`.

**Escenario y reproducción:** después del POST, Higgsfield devuelve HTTP 200 con texto no JSON y produce `JSONDecodeError`; un JSON lista produce `TypeError`. APIMart con `{"data":["broken"]}` y KIE con `[]` producen `AttributeError`. El worker solo captura `ProviderError`. La excepción sale tras el reclamo persistido, por lo que el Job queda en `submitting`, sin error visible ni request ID. El timeout no incluye ese estado.

Con el cuerpo de APIMart anterior, confirmé **un envío, excepción `AttributeError` y estado `submitting`**. Adelantar su antigüedad un día y ejecutar `expire` no lo termina. Solo el reinicio lo clasificaría después como ambiguo.

**Arreglo sugerido:** validar el tipo y estructura de toda respuesta de envío y envolver los errores de parsing como `ambiguous`, conservando un estado terminal revisable sin reintentar. No liberar el Job para otro POST como recuperación. Añadir cuerpos no JSON, listas y listas con elementos inválidos para los tres adaptadores.

### 6. ALTA: los endpoints gratuitos de audio siguen abriendo el MPD de una subida anterior

**Ubicación:** `src/hf_studio/api.py:956`, `src/hf_studio/api.py:1194`, `src/hf_studio/voice.py:257`, `src/hf_studio/audio.py:67`.

**Escenario:** la base contiene un Upload propio aceptado antes de esta corrección, cuando `/uploads` admitía un manifiesto DASH declarado como MP4. La nueva subida lo rechaza y `complete_hints` ahora es seguro, pero `/v1/voice/estimate` y `/v1/audio/voice-isolator/estimate` siguen pasando la URL remota a `probe_duration`. La pertenencia al propietario sigue siendo su comprobación de confianza. Estas rutas mantienen ffprobe con red y sin la whitelist de contenedores nueva.

**Reproducción con ffprobe real:** simular ese registro anterior en la SQLite temporal y servir el mismo MPD de la ronda 28 desde HTTPS. **Ambos endpoints de estimación hicieron GET /uploaded.mp4 seguido de GET /internal.mp4** en loopback. Acabaron con 422, después de la petición interna. No se llamó a ningún servicio de audio pagado.

**Límite:** no es un bypass demostrado de las subidas nuevas. Una base limpia no introduce este MPD por `/uploads`, que ahora devuelve 415. Es un camino todavía vulnerable con medios ya registrados y deja incompleta la protección del flujo de medios al actualizar una instalación existente.

**Arreglo sugerido:** usar la descarga controlada y medición sin red también en voz y aislamiento; adaptar los contenedores admitidos a audio y video. Aplicar la misma política al procesamiento posterior de esas fuentes. No considerar validado un archivo anterior únicamente porque tiene una fila de Upload o pertenece a una generación.

### 7. ALTA: una carrera con la limpieza de quotes MCP puede eliminar el límite aprobado

**Ubicación:** `src/hf_studio/mcp_server.py:188`, `src/hf_studio/mcp_server.py:197`, `src/hf_studio/mcp_server.py:590`, `src/hf_studio/mcp_server.py:616`, `src/hf_studio/mcp_server.py:683`, `src/hf_studio/mcp_server.py:755`.

**Escenario:** un hilo canjea una cotización justo antes de vencer y libera `_quotes_lock`. Antes de que lea su precio mediante `_quoted_usd`, se alcanza el vencimiento y otro hilo emite una cotización: `_issue_quote` borra la anterior. `_quoted_usd` retorna `None` en lugar del importe aprobado. La generación, lote o preset termina enviándose sin techo numérico, aunque la cotización original sí tenía uno. La API interpreta `None` como ausencia de límite y acepta el precio que encuentre en ese momento.

**Reproducción:** acortar en memoria el tiempo restante de un quote de 0,71 USD a 10 ms; después de una redención válida, simular una pausa de 20 ms y la emisión de otro quote antes de la lectura separada del precio. El cuerpo de `generate` lleva **`max_usd=None`**. Es una intercalación controlada de expiración y limpieza; no se generó nada real. Los locks actuales hacen atómica la elección de la clave, pero no la captura de los datos de autorización.

**Arreglo sugerido:** devolver desde la redención, bajo el mismo lock, una copia de la clave y de toda la autorización de costo. Construir la petición a partir de esa copia. Nunca convertir una cotización desaparecida en permiso sin límite; si no puede recuperarse la autorización, fallar antes de llamar a la API.

### 8. MEDIA: `confirm_unknown_cost=True` ya no permite ejecutar un lote sin total completo

**Ubicación:** `src/hf_studio/mcp_server.py:683`, `src/hf_studio/api.py:678`, contrato de `generate_batch` en `src/hf_studio/mcp_server.py:677`.

**Escenario:** `total()` devuelve siempre un número en `usd`, incluso cuando `complete=False`; es la suma parcial, o cero si no se conoce ningún importe. El MCP acepta la confirmación explícita de costo desconocido, pero envía ese subtotal como `max_total_usd`. La API lo trata como un techo de precio conocido y rechaza cualquier ítem sin precio. Se contradice el comportamiento documentado de `confirm_unknown_cost`.

**Reproducción:** proveedores falsos sin cifras disponibles: el dry-run devuelve **`{"usd":0.0,"complete":false}`**. Canjear el quote con `confirm_unknown_cost=True` envía `max_total_usd=0.0`; la API responde **409 `cost_unknown`**. Para un lote parcialmente cotizado ocurre lo mismo con su subtotal. No hubo envíos a proveedores.

**Arreglo sugerido:** distinguir en la autorización el techo completo aprobado de la aceptación explícita de precio desconocido. No convertir un subtotal en presupuesto. Propagar esa decisión de forma coherente al Job y a la recotización posterior, o retirar explícitamente este modo del producto y de su contrato; no anunciarlo mientras queda imposible de usar.

## Decisión sobre costo final estimado y reserva

**Separar `max_usd` de la reserva es razonable como decisión de producto, pero no acepto la implementación actual.** Puede significar «máxima estimación final que acepto», mientras la reserva se informa y autoriza por separado. Debe quedar claro que una estimación liquidada por tokens no es una garantía contractual del débito final, y que la reserva afecta inmediatamente al saldo.

No exijo que ambos importes sean el mismo campo. Sí exijo que la reserva consentida sobreviva a la cotización y que un respaldo no introduzca una retención mayor sin mostrarla y obtener aprobación. Hoy el primer panel puede mostrarla, pero el respaldo y su aprobación la pierden, como demuestra el hallazgo 3. Una instrucción al agente para mencionarla y una comprobación de saldo no sustituyen esa autorización.

El ejemplo de 8 s sigue teniendo 2,0736 USD estimados y 4,9248 USD de reserva, coherente con la [documentación de Seedance 2.5 de APIMart](https://docs.apimart.ai/en/api-reference/videos/seedance-2-5/generation.md), que reserva hasta 30 s de salida para `duration=-1` y liquida después. El cambio a `approx` y el filtro de saldo por reserva son mejoras correctas.

## Comprobación de los nueve puntos de la ronda 28

| Punto anterior | Resultado de esta ronda |
| --- | --- |
| 1. Carrera de sondeo/webhook | La reproducción ahora rechaza el segundo commit viejo y envía KIE una sola vez. Dos aprobaciones concurrentes dieron 200/409; cancelar antes de completar la aprobación dejó `canceled` y la aprobación obtuvo 409. |
| 2. Envío ambiguo | Las respuestas ordinarias sin ID y el 502 pasan a ambiguas. Persisten el 503 genérico y cuerpos malformados de los hallazgos 1 y 5. |
| 3. Lotes/presets | Los casos repetidos con sus límites enviados responden 409 al subir de 0,71 a 1,025 USD. El límite numérico se propaga en MCP y UI. Existe la regresión del modo desconocido del hallazgo 8. |
| 4. Precio desconocido y tolerancia | El precio perdido con tope devuelve 409 `cost_unknown`; los tests comprueban rechazo de 0,71 USD ante un techo menor. La tolerancia monetaria anterior fue eliminada. |
| 5. MPD/ffprobe | La subida nueva devuelve 415. `local_duration` descarga el MPD pero no abre su referencia interna; ffprobe real con las restricciones nuevas rechaza el demuxer DASH sin hacer peticiones de red. Persisten los caminos de audio del hallazgo 6. |
| 6. Reserva | El estimador devuelve la reserva correcta y excluye APIMart con saldo insuficiente. Se pierde al persistir y aprobar el respaldo, hallazgo 3. |
| 7. Edición/extensión en KIE | Las dos rutas ya no están en el mapa KIE. |
| 8. Parámetros descartados | Las seeds fijas de Wan 2.6 y HappyHorse v1.1 se rechazan en KIE; bitrate explícito se rechaza en ambos revendedores. Confirmado con los traductores reales. |
| 9. Recotización | Aprobar 1,025 USD cuando la tabla indica 2,50 da 409. Un plan de más de 15 minutos se detiene al subir el precio. Persisten el cambio dentro del TTL y la recuperación del panel de aprobación, hallazgos 2 y 4. |

## Validación y límites

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **305 passed, 2 skipped**.
- Ruff check: **All checks passed**. Ruff format en modo `--check`: **47 files already formatted**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit`: código 0.
- `git diff --check 461369b^..461369b`: sin errores.
- ffprobe real: MPD rechazado por la whitelist de formatos, sin petición interna; un MP4 válido generado en `/tmp` midió **1,0 s** con `local_duration`.
- Scripts propios en `/tmp` repitieron las carreras, lotes, presets, subida/medición de MPD, recotizaciones y traducciones. También reprodujeron los ocho escenarios anteriores sin gasto real.
- No hice pruebas manuales del producto ni automatización de navegador. La conclusión sobre el botón de aprobación se apoya en sus llamadas reales y en los GET/POST de la API falsa.
- No verifiqué cobros o reembolsos reales. Las cifras de las reproducciones salen de las tablas aportadas o de cambios controlados para simular variaciones de tarifa. No encontré una fuga directa nueva de claves.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Tratar los 503 genéricos de envío de APIMart/Higgsfield como ambiguos, sin reintentos ni respaldo salvo garantía explícita de rechazo.
2. Detectar cambios de tarifa conocidos antes de enviar, aunque el quote tenga menos de 15 minutos, y respetar `max_usd` también en respaldos.
3. Persistir, recotizar, publicar y autorizar la reserva por separado de la estimación final, incluida la aprobación de respaldos en UI y MCP.
4. Permitir que la UI muestre y apruebe explícitamente una recotización después de `cost_changed`, sin reutilizar eternamente el importe antiguo.
5. Convertir todas las respuestas de envío malformadas en fallo ambiguo revisable, evitando Jobs atascados en `submitting`.
6. Aplicar la protección de medios sin red a las estimaciones/procesamientos de audio que todavía abren URLs confiando solo en su registro, incluidos medios anteriores a la corrección.
7. Capturar atómicamente clave y autorización de costo al canjear un quote MCP, evitando la pérdida del techo por expiración y limpieza concurrentes.
8. Hacer coherente la aceptación explícita de costo desconocido del lote con la API y su recotización, o retirar ese modo y su promesa de forma explícita.
