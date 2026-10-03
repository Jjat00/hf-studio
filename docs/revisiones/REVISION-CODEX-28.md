# Revisión adversarial 28: multiproveedor

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD `b3cb108`. Revisados `git log e6a46a8..HEAD` y los cambios de `fb74098`, `c102202`, `75f5f52` y `b3cb108`.

Objetivo evaluado: mismo modelo y pedido, proveedor más barato, precio previo aprobado y respaldo automático únicamente sin cobro previo y dentro de `max_usd`. Higgsfield mantiene las subidas de medios.

No modifiqué código ni hice generaciones reales, subidas reales o llamadas que gastaran créditos. Las reproducciones usan ASGI, SQLite temporal, `httpx.MockTransport`, las tablas de `tests/fixtures/prices_*.json` y, para ffprobe, un servidor HTTPS temporal en loopback. Consulté documentación pública mediante lecturas gratuitas. No leí secretos de `.env`. El archivo preexistente `tt.png` quedó intacto.

## Hallazgos

### 1. CRÍTICA: un sondeo/webhook tardío puede enviar dos veces el mismo respaldo

**Ubicación:** `src/hf_studio/worker.py:278`, `src/hf_studio/worker.py:301`, `src/hf_studio/worker.py:227`; disparador concurrente en `src/hf_studio/api.py:1452`.

**Escenario:** worker y webhook cargan en sesiones distintas el mismo trabajo `queued` de APIMart. Ambos consultan su fallo. El primero aplica `fallback`, guarda `pending` en KIE y el worker envía KIE. El segundo aplica el fallo sobre su objeto anterior y sobrescribe el trabajo de KIE con `pending`, limpiando su request ID. El siguiente ciclo vuelve a enviar KIE. Reclamar atómicamente `pending` no protege contra esta escritura tardía. La guarda de terminalidad comprueba el objeto viejo de SQLAlchemy, no el estado actual de la fila.

**Reproducción confirmada:** con `tests/test_routing.py::env`, crear Seedance 2.0 con `max_usd=2`, enviar APIMart, cargar el Job en dos sesiones, aplicar `Polled('failed')` en A y commit, `worker.submit(id)`, aplicar el mismo fallo en B y commit, `worker.submit(id)`. Resultado: **2 POST de KIE para un único Job**. Ninguno de esos dos respaldos tiene por qué fallar o reembolsarse.

La misma ausencia de control de versión permite que un resultado antiguo sobrescriba una cancelación. Además, el CAS de `approve` en `api.py:713` solo compara `status`: no distingue una espera de aprobación anterior de otra posterior.

**Arreglo sugerido:** aplicar cada resultado mediante CAS de la identidad del intento: proveedor, request ID, índice/versionado del plan y estado esperado. Serializar las transiciones por Job y descartar resultados de intentos anteriores. Aprobar y cancelar con esa misma identidad. Añadir una regresión con dos sesiones, intercalando el envío del respaldo entre ambas respuestas, y otra con cancelación.

### 2. ALTA: respuesta de envío sin ID y errores 5xx se consideran seguros para cobrar de nuevo

**Ubicación:** `src/hf_studio/providers/apimart.py:124`, `src/hf_studio/providers/kie.py:114`, `src/hf_studio/providers/base.py:41`, `src/hf_studio/worker.py:196`.

**Escenario:** el proveedor acepta y cobra la tarea, pero su respuesta HTTP 200 pierde el identificador, o una capa intermedia devuelve 502/503 después de que el backend la aceptara. Los adaptadores clasifican la ausencia de ID como `server`; `server` es tanto `retryable` como `fallback_safe`. El worker repite el POST y, al agotar intentos, puede cambiar de proveedor. La ausencia de task ID no demuestra que no exista tarea. Un error HTTP genérico posterior al POST tampoco lo demuestra.

**Reproducción confirmada:** con `MockTransport` devolviendo HTTP 200 y `{"code":200,"data":{}}`, **ambos adaptadores lanzan `server`, `retryable=True`, `fallback_safe=True`**. Higgsfield también comparte la clasificación de errores HTTP 5xx. Los timeouts de lectura sí se clasifican correctamente como ambiguos; esa protección no cubre estas respuestas.

**Arreglo sugerido:** tratar respuestas exitosas sin ID, respuestas ilegibles tras envío y 5xx sin garantía documentada de rechazo como `ambiguous`, sin reintento ni respaldo. Reservar la condición de fallo seguro para rechazos explícitos que garanticen ausencia de tarea/cobro, o usar idempotencia remota verificable si el proveedor la admite.

### 3. ALTA: lotes y presets ejecutan un precio distinto del aprobado en MCP y UI

**Ubicación:** `src/hf_studio/api.py:648`, `src/hf_studio/api.py:869`, `src/hf_studio/mcp_server.py:679`, `src/hf_studio/mcp_server.py:749`, `web/src/components/presets/preset-runner.tsx:95`, `web/src/lib/studio.ts:156`.

**Escenario:** `generate_batch` o `run_preset` obtiene un `quote_id` para APIMart, el usuario aprueba y antes de ejecutar sube la tarifa, desaparece una fila o cambia el saldo. El MCP verifica los parámetros y el uso del quote, pero no envía su precio como límite. La API recalcula el plan y guarda como `max_usd` el precio nuevo, mediante el valor por defecto de `create_generation`. Se genera directamente con ese precio. La UI de presets tampoco transmite el precio que acaba de mostrar.

**Reproducción confirmada:** lote de un Seedance 2.0, 720p, 5 s: `dry_run` devuelve **0,71 USD**. Cambiar la tarifa APIMart de la caché a 0,30 USD/s y ejecutar el mismo lote devuelve **202 y 1,025 USD en KIE**, sin aprobación adicional.

**Arreglo sugerido:** propagar y verificar la cotización aprobada en lotes y presets, incluyendo límites por ítem y total antes de crear el primer Job. Pasar esos límites al servicio, MCP y UI. Un cambio de precio debe devolver `cost_changed` o esperar aprobación; nunca convertir automáticamente el precio nuevo en aprobado. Para presets, vincular también la cotización a la entrada final renderizada.

### 4. ALTA: un límite numérico aprobado permite enviar una generación cuyo precio pasó a desconocido

**Ubicación:** `src/hf_studio/api.py:543`; tolerancia compartida en `src/hf_studio/api.py:706`.

**Escenario:** se cotiza y aprueba 0,71 USD. Al recalcular, el proveedor elegido ya no tiene cifra, por ejemplo porque una sincronización perdió la fila de precios. La condición exige `best.usd is not None`; si es `None`, omite el control de `max_usd` y pone el Job en cola. MCP `generate` sí transmite el precio del quote, pero la API no lo hace respetar en este caso. El usuario aprobó una cifra, no un costo desconocido.

**Reproducción confirmada:** cotizar Seedance 2.0 con `provider='apimart'`, retirar su tabla de la caché y crear con el mismo proveedor y `max_usd=0.71`: **202, `cost_usd=None`**.

Además, la tolerancia fija de **0,005 USD** admite importes superiores al techo declarado: 0,71 USD pasa con `max_usd=0.706`. No es un epsilon numérico, sino permiso de gasto adicional. `approve` también puede elevar el techo por esa tolerancia.

**Arreglo sugerido:** cuando hay límite numérico, rechazar costo desconocido o incompleto y solicitar otra cotización. La autorización de precio desconocido debe ser explícita y distinta. Comparar dinero con Decimal/unidades enteras o un epsilon de cálculo mínimo, sin ampliar el presupuesto del usuario.

### 5. ALTA: SSRF a través del contenido de un medio propio medido con ffprobe

**Ubicación:** `src/hf_studio/api.py:423`, aceptación de subidas en `src/hf_studio/api.py:483`, `src/hf_studio/audio.py:67`, `src/hf_studio/audio.py:78`.

**Escenario:** un cliente autenticado sube bytes de un manifiesto DASH declarando `video/mp4`. La subida comprueba el tipo declarado, pero no el contenido. Su URL de Higgsfield pasa `trusted_media`, porque es una subida propia. Al cotizar un modelo con `video_url` sin hints, ffprobe autodetecta DASH y abre las URLs de segmentos incluidas por el cliente. Que la URL inicial sea de confianza no hace confiable el contenido ni sus referencias. La whitelist de protocolos permite HTTPS y TCP, incluidas direcciones privadas.

**Reproducción confirmada:** servir `/uploaded.mp4` con un XML MPD cuyo `Representation/BaseURL` apunta a `https://127.0.0.1:<puerto>/internal.mp4`. Ejecutar la función real `probe_duration` produjo **GET /uploaded.mp4 seguido de GET /internal.mp4**, con ffprobe 6.1.1. Se repitió con las mismas opciones de `audio.duration`. La medición finalmente devolvió `None`, pero la petición interna ya ocurrió. El XML funciona aun con extensión `.mp4`; no depende de una URL `.m3u8` ni de aceptar un MIME de playlist.

**Arreglo sugerido:** descargar el medio autorizado con validación de destino/redirecciones y medir un archivo local, restringiendo formato y protocolos de ffprobe para impedir referencias de red o a otros archivos. Validar el contenedor real de las subidas y rechazar manifiestos. La medición debe ejecutarse sin acceso a red; filtrar únicamente la URL inicial no basta.

### 6. ALTA: Seedance 2.5 edit cotiza el costo final estimado pero omite un débito inicial mayor

**Ubicación:** `src/hf_studio/providers/apimart_routes.py:64`, `src/hf_studio/providers/apimart_routes.py:125`, `src/hf_studio/routing.py:189`.

**Escenario:** editar una fuente de 8 s a 720p fija `duration=-1`. El estimador supone 8 s de entrada + 8 s de salida y etiqueta la cifra como `exact`. La [documentación de Seedance 2.5 de APIMart](https://docs.apimart.ai/en/api-reference/videos/seedance-2-5/generation.md), apartados de tipos de tarea y Billing, especifica que `-1` reserva inicialmente hasta 30 s de salida y liquida después la duración real.

Con la tabla real `seedance-2.5|720P-input=0.1296`, se muestran **2,0736 USD** por 16 s, pero el débito/reserva inicial es **4,9248 USD** por 8+30 s. Que parte se devuelva después no elimina el gasto inicial no mostrado. El filtro de saldo también compara con la cifra menor y puede seleccionar una cuenta que no alcance para la reserva.

**Arreglo sugerido:** representar por separado costo final estimado y débito/reserva máxima inicial; mostrar y aprobar ambos, usando la reserva para comprobar saldo. No marcar como exacto un costo aún sujeto a liquidación. Si `max_usd` limita el débito, verificar 4,9248 USD antes de enviar este ejemplo.

### 7. ALTA: KIE sustituye edición y extensión de Seedance por generación con referencias

**Ubicación:** `src/hf_studio/providers/kie_routes.py:91`, `src/hf_studio/providers/kie_routes.py:98`.

**Escenario:** un pedido lógico `bytedance/seedance-2.5/video-edit` o `video-extend` se transforma en el mismo endpoint de generación multimodal con el video como primera referencia. No se transmite una operación edit/extend. Las propias notas admiten que KIE no tiene modo explícito. El prompt válido del catálogo puede ser simplemente «Una playa al atardecer»: el traductor no exige intención de edición/extensión ni garantiza que el clip se edite o continúe. El resultado puede ser una nueva generación basada en referencias, cobrada como éxito.

La [documentación pública de KIE Seedance 2.5](https://docs.kie.ai/market/bytedance/seedance-2-5) describe generación con referencias y no establece en esa página el contrato de edición/extensión usado por estas rutas. La falta de garantía, junto con la sustitución explícita reconocida en el código, impide tratar esas operaciones como traducciones fieles automáticas. APIMart, en cambio, sí transmite `omni_reference_task_type`.

**Arreglo sugerido:** excluir estas dos rutas de KIE mediante `unsupported` hasta demostrar una operación equivalente que preserve edición/extensión y duración. Una aproximación por prompt puede ofrecerse aparte con consentimiento específico, pero no participar del respaldo automático del mismo pedido.

### 8. MEDIA: se descartan seeds explícitas y bitrate sin comprobar equivalencia

**Ubicación:** `src/hf_studio/providers/kie_routes.py:193`, `src/hf_studio/providers/kie_routes.py:273`, `src/hf_studio/providers/kie_routes.py:76`, `src/hf_studio/providers/apimart_routes.py:85`; presentación en `web/src/components/studio/cost-panel.tsx:124`.

**Escenario y prueba:** `wan/v2.6/text-to-video` con `seed=123`, válido en el catálogo, llega a KIE sin seed. Lo mismo sucede con HappyHorse v1.1. Ambas conversiones devuelven `None` para cualquier valor, en lugar de rechazar las semillas fijas. Seedance 2.5 con `bitrate_mode='standard'` y con `'high'` produce la misma entrada traducida en ambos revendedores: el campo se descarta incondicionalmente, aunque el catálogo distingue las dos calidades y usa `high` por defecto.

Las notas de algunas rutas no corrigen la pérdida ni constituyen aprobación. El panel comparativo de la UI muestra proveedor, precio y canal, pero no esas notas, por lo que quien aprueba no ve la degradación. Las reproducciones de los traductores confirmaron las omisiones.

**Arreglo sugerido:** rechazar con `unsupported` semillas fijas que el proveedor no pueda reproducir. Traducir bitrate o admitir únicamente un valor cuya equivalencia esté comprobada; excluir los demás. Si una degradación se ofrece voluntariamente, mostrarla y pedir consentimiento fuera del ruteo fiel automático.

### 9. ALTA: aprobar un respaldo no verifica su precio vigente

**Ubicación:** `src/hf_studio/api.py:704`, `src/hf_studio/worker.py:178`, `src/hf_studio/providers/prices.py:46`.

**Escenario:** un trabajo espera aprobación y su plan almacenado conserva el precio de KIE. Después cambia la tarifa, incluso con la caché local ya sincronizada. `approve` compara `max_usd` únicamente con el importe antiguo del plan, y el worker envía esa opción sin recotizar. La espera no expira y el plan puede tener días de antigüedad. Esto también afecta trabajos pendientes demorados y tablas viejas conservadas tras errores de sincronización: siguen presentándose como `exact`.

**Reproducción confirmada:** Seedance 2.0 falla en APIMart y espera aprobar KIE por **1,025 USD**. Actualizar la fila KIE de 720p sin video a 0,50 USD/s hace que `/v1/estimate` con KIE devuelva **2,50 USD**. `POST /approve` con `max_usd=1.025` responde **200**, deja el costo almacenado en 1,025 y permite el envío.

**Arreglo sugerido:** volver a cotizar la opción antes de aprobar y antes de enviar si la cotización venció o cambió su versión. Si supera el techo, mantener `awaiting_approval` y mostrar el nuevo precio. Guardar fecha/versionado y vencimiento de la cotización; no convertir una tabla caducada indefinidamente en precio exacto autorizado.

## Comprobaciones y límites

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **295 passed, 2 skipped**. El primer intento con la caché predeterminada falló por permisos de solo lectura; se resolvió usando `/tmp`.
- `uv run ruff check src tests`, con esa caché: **All checks passed**.
- `uv run ruff format --check src tests`, con esa caché: **46 files already formatted**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit`: **código 0**. No se ejecutaron pruebas manuales de producto ni automatización de navegador.
- `git diff --check e6a46a8..HEAD`: sin errores.
- Las reproducciones temporales confirmaron duplicación de respaldo, cambio de precio en lote, precio desconocido con techo numérico, clasificación insegura de respuestas sin ID, campos descartados, SSRF y aprobación con precio antiguo.
- Los tests actuales prueban traducciones típicas y que exista algún precio positivo, pero no prueban equivalencia de todos los valores del catálogo, reservas iniciales ni estas intercalaciones concurrentes.
- `/v1/webhooks/{provider}/...` consulta el estado autoritativo y exige el token del Job; no encontré una falsificación directa del estado por el cuerpo recibido. El problema bloqueante es la aplicación concurrente del resultado, hallazgo 1.
- `/providers` muestra estado/saldo sin exponer claves en su respuesta ordinaria. Los clientes separan descargas sin credenciales de los clientes autenticados. No encontré una fuga directa de claves en las superficies revisadas.
- Las subidas siguen pasando por Higgsfield y el contrato/registro facilita incorporar proveedores. Esto no compensa los fallos de autorización, seguridad y fidelidad anteriores.
- No se verificaron cobros/reembolsos reales. El cálculo de la reserva de Seedance se deriva de la documentación pública y de las tablas reales aportadas, no de una generación pagada.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Impedir que sondeos/webhooks antiguos o carreras de aprobación/cancelación reescriban otro intento y dupliquen envíos, con regresiones concurrentes.
2. Clasificar como ambiguos los envíos sin identificación o sin garantía de rechazo, eliminando sus reintentos y respaldos automáticos.
3. Hacer cumplir el precio aprobado en lotes y presets, tanto en MCP como en UI/API, antes de crear trabajos.
4. Bloquear costo desconocido/incompleto bajo un techo numérico y eliminar la tolerancia monetaria que amplía ese techo.
5. Impedir referencias de red/archivos desde medios medidos con ffprobe, incluida la reproducción DASH presentada como `.mp4`.
6. Mostrar, aprobar y comprobar saldo para la reserva inicial real de Seedance 2.5 edit, separándola del costo final estimado.
7. Excluir de KIE las rutas edit/extend sin equivalencia demostrada, o implementar una traducción fiel verificada.
8. Preservar o rechazar seeds y bitrate explícitos; ninguna degradación puede entrar silenciosamente en el ruteo automático.
9. Recotizar respaldos y envíos con precios vencidos/cambiados, conservando el techo aprobado y solicitando aprobación cuando corresponda.
