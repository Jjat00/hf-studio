# Revisión adversarial de Codex, ronda 32

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD **`aa0e721`**. Revisados `git show c9ae337 aa0e721`, el diff contra `5989735` y los flujos completos de autorización, envío, respaldo, deduplicación, MCP y UI. Las reproducciones propias se ejecutaron sobre una copia de `git archive aa0e721` en `/tmp/hf-review32-aa0e721`.

Todos los proveedores se simularon con `httpx.MockTransport`, claves falsas y bases/almacenamiento temporales. Para medios utilicé ffprobe/ffmpeg reales y HTTPS en loopback. No repetí la prueba F0 contra proveedores reales, no gasté créditos y no modifiqué código. Solo añadí este informe; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: una aprobación rechazada añade permiso de costo desconocido, que una aprobación posterior explícitamente limitada no elimina

**Ubicación:** `src/hf_studio/api.py:835`, `src/hf_studio/api.py:853`, `src/hf_studio/api.py:857`, `src/hf_studio/routing.py:239`, `src/hf_studio/worker.py:287`.

**Escenario:** `/approve` incorpora `unknown_accepted=True` a `fresh` antes de comprobar precio y retención. Si rechaza la aprobación con 409, guarda esa misma opción como la cotización actual. Con ello persiste también una autorización que no llegó a aprobarse. Después, `requote` copia el flag de la opción anterior; una aprobación exitosa con `accept_unknown_cost=false` no lo elimina. Si desaparece la tarifa antes del envío, el worker permite el POST por ese permiso residual, aunque la aprobación exitosa solo autorizó un precio conocido y limitado.

**Reproducción:**

1. Crear Seedance 2.0, 720p, 5 s con techo de **0,71 USD**. APIMart falso rechaza por saldo, sin cobrar, y KIE queda esperando aprobación a **1,025 USD**.
2. Llamar a `/approve` con `{"max_usd":1,"accept_unknown_cost":true}`. Devuelve **409 `cost_changed`**. La opción KIE persistida ya contiene **`unknown_accepted=True`**, aunque la petición fue rechazada.
3. Aprobar el precio conocido con `{"max_usd":1.025,"accept_unknown_cost":false}`. Devuelve **200** y conserva aquel flag.
4. Vaciar la tabla KIE antes de enviar. El worker recotiza a **`usd=None`**, hace **un POST simulado a KIE** y deja el trabajo `queued`, publicando **`max_usd=1.025`**.

No se demostró un cobro duplicado. Se demostró un envío con costo desconocido después de una aprobación exitosa que lo excluía explícitamente; la aceptación provino de una petición rechazada. La desaparición de la tarifa debería haber detenido ese envío.

**Arreglo sugerido:** separar los datos de cotización de los permisos de aprobación. El 409 puede actualizar importes, pero no añadir autorizaciones de la petición rechazada. En el CAS exitoso, guardar el permiso correspondiente a la aprobación actual, incluyendo `False`, en vez de heredar el flag mediante `requote`. Conservar una autorización anterior solo cuando corresponda a una aprobación válida que siga vigente. Verificar la secuencia 409 → aprobación conocida con aceptación falsa → pérdida de tarifa: debe quedar en `awaiting_approval`, sin POST.

### 2. MEDIA: una aceptación sin techo pierde su naturaleza si la tarifa reaparece entre la cotización y la creación

**Ubicación:** `src/hf_studio/api.py:511`, `src/hf_studio/api.py:514`, `src/hf_studio/service.py:144`, `src/hf_studio/api.py:1040`.

**Escenario:** el MCP cotiza un precio desconocido y transmite correctamente `accept_unknown_cost=true`, `max_usd=None`. Antes de crear el trabajo, vuelve a estar disponible una tarifa. `authorize` devuelve `None` para expresar la autorización sin techo, pero `create_generation` interpreta ese `None` como «usar el precio del plan» y fija un techo numérico. Además, `authorize` solo añade `unknown_accepted` si el precio sigue desconocido en ese instante, así que tampoco conserva el permiso explícito. El resultado contradice el comportamiento anunciado de esta corrección y puede pedir una aprobación adicional aunque el usuario ya aceptó esta opción sin techo.

**Reproducción con el propio MCP:** vaciar la tabla APIMart y cotizar Seedance 2.0 forzado en APIMart. Emitir el quote y llamar a `generate(..., confirm_unknown_cost=True)` capturando su cuerpo: contiene **`max_usd=None`, `accept_unknown_cost=true`**. Restaurar la tarifa real de **0,71 USD** antes de entregar ese cuerpo a REST. La respuesta 202 y la fila del Job tienen **`max_usd=0.71`**, y la opción no tiene `unknown_accepted`. Subir luego la tarifa a **1,50 USD** y enviar: **`awaiting_approval`, cero envíos**, pese a la autorización sin techo de la misma opción forzada.

También reproduje el mismo cambio entre dry-run y creación de un preset: el dry-run tenía precio desconocido, el POST aceptaba explícitamente sin techo, el Job adoptó **0,71 USD como límite** y el aumento a 1,50 lo dejó esperando aprobación.

**Arreglo sugerido:** distinguir «no se proporcionó presupuesto» de «se proporcionó explícitamente una autorización sin techo» al llamar a `create_generation`, por ejemplo mediante un sentinel o un objeto de autorización. Persistir el `None` explícito y conservar la aceptación de la opción autorizada aunque su precio reaparezca antes de guardarla. No extenderla a otros proveedores ni a reservas nuevas. Cubrir generación y presets cuando la tarifa pasa de desconocida a conocida entre quote y POST, además del cambio posterior antes del envío.

## Repetición de los tres hallazgos de la ronda 31

| Caso | Resultado en `aa0e721` |
| --- | --- |
| Techo numérico al reaparecer la tarifa | Creación APIMart con aceptación de desconocido y techo 0,71 USD: al aparecer 1,50, queda **`awaiting_approval`, cero envíos**. En respaldo KIE aprobado con techo 0,71: al aparecer 2,50, también queda esperando, **cero envíos KIE**. |
| Preset UI de precio desconocido | El formulario y `studio.runPreset` envían el flag después de la confirmación. Con todas las opciones aún desconocidas, el cuerpo equivalente crea un Job que termina **`queued`, un envío simulado**, sin la aprobación imposible anterior. Pendiente la transición del hallazgo 2. |
| Aprobar desconocido por MCP/UI | El propio `approve_fallback(..., accept_unknown_cost=True)` envía **`max_usd=None` y el flag**. REST devuelve 200, guarda `max_usd=None` y el worker envía una vez a KIE. La tarjeta habilita la acción y muestra «Aprobar costo desconocido»; usa esa modalidad sin techo y mantiene la retención separada. Inspección de código y reproducción de API, sin automatizar navegador. |

## Deduplicación y regresiones anteriores

- **Proveedor forzado:** misma entrada forzada en APIMart y KIE crea dos Jobs distintos; repetir KIE devuelve el suyo. Repetir selección automática devuelve el mismo Job automático. Reutilizar una `Idempotency-Key` para otro proveedor forzado devuelve **409**, sin crear otro trabajo con esa clave. La huella nueva conserva la idempotencia y respeta el proveedor elegido.
- **Costo desconocido y retención:** el MCP conserva la reserva vista de 4,9248 USD en un lote incompleto. Duplicar la tarifa que la lleva a 9,8496 devuelve **409 `reserve_not_approved`**, sin envío. Una generación sin techo final pero con reserva aprobada de cero también se rechaza antes de crear.
- **Proveedor más barato:** APIMart pasa de 0,71 a 1,50 USD con techo de 2 USD; el replan envía a **KIE por 1,025 USD**, un POST KIE y cero APIMart.
- **503 y respuestas malformadas:** ID ausente, texto no JSON, listas inesperadas y 503 siguen como `ambiguous`, sin reintento ni respaldo en los tres adaptadores. El worker con 503 o `data:["broken"]` termina `failed/submission_ambiguous`, con un envío APIMart y cero KIE.
- **Carreras:** dos aprobaciones producen 200/409; cancelación que gana conserva `canceled` y rechaza aprobar. Un resultado de sondeo obsoleto pierde el CAS y no duplica el respaldo. La limpieza concurrente de quotes conserva `max_usd=0.71` en el cuerpo MCP.
- **UI tras 409:** la cotización nueva de KIE, 2,50 USD, se publica en la generación, evitando que el botón conserve el importe antiguo. El hallazgo 1 afecta al permiso añadido junto con esa actualización.
- **Medios:** dos descargas concurrentes de la misma URL terminan correctamente con temporales propios. El MPD nuevo devuelve 415. Voz y aislamiento sobre un Upload anterior descargan solo el archivo fuente y responden 422, sin GET de la URL interna del manifiesto. ffprobe real lo rechaza por whitelist; un MP4 real válido mide 1,0 s.
- **Traducción y precios:** los aumentos de lotes/presets y el desconocido bajo techo sin aceptación siguen rechazándose; seed/bitrate explícitos sin equivalente siguen como `unsupported`; KIE mantiene retiradas las rutas Seedance edit/extend. No encontré una nueva fuga de claves ni un bypass de las restricciones de ffprobe en lo revisado.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **324 passed, 2 skipped**.
- `uv run ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Las reproducciones adicionales usaron la copia exacta de `aa0e721`, tablas de `tests/fixtures/prices_*.json`, bases temporales y métodos simulados en memoria. No se modificaron fuentes del repositorio ni se llamaron endpoints pagados reales.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Evitar que una aprobación rechazada añada permiso para costo desconocido y que ese permiso sobreviva a una aprobación posterior que establece explícitamente `accept_unknown_cost=false`; sin autorización válida, una tarifa perdida debe detener el envío.
2. Conservar la autorización explícita sin techo y su permiso para la misma opción cuando la tarifa reaparece entre cotización y creación, en generación y presets, sin convertir `max_usd=None` en el precio actual del plan.
