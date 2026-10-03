# Revisión adversarial de Codex, ronda 36

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD **`7edaef5`**. Revisados `git show HEAD`, las nuevas pruebas y las protecciones acumuladas del flujo multiproveedor.

Reproducciones independientes sobre una copia de `git archive HEAD` en `/tmp/hf-review36-7edaef5`, con proveedores simulados mediante `httpx.MockTransport`, claves falsas, bases y almacenamiento temporales. Para medios utilicé ffprobe/ffmpeg reales y HTTPS en loopback. **Sin generaciones reales, sin gasto de créditos y sin modificar código.** El informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

**No encontré hallazgos nuevos que requieran corrección en el alcance revisado.** El punto de la ronda 35 está corregido: `src/hf_studio/providers/kie.py:37` trata primero los códigos >= 500, limita la excepción de validación al mensaje conocido y evita que la detección de moderación convierta esos errores en rechazos seguros. Los antiguos 501/505 ya no habilitan reintento o respaldo.

## Reproducción del hallazgo de la ronda 35

Selección automática de Seedance 2.0, 720p, 5 s, con **KIE primero por 1,025 USD**, Higgsfield como respaldo por **1,51 USD** y `max_usd=2`. APIMart sin tarifa para este control. Cada fila se ejecutó en un entorno independiente, registrando los POST y avanzando tres ciclos del worker.

Todas las respuestas KIE usan HTTP 200 y el código indicado dentro del JSON, con `data:null`:

| Código | Mensaje | Resultado |
| --- | --- | --- |
| 500 | `Internal Server Error` | `ambiguous`, sin respaldo. |
| 500 | `Internal server error: invalid response from upstream` | `ambiguous`, sin respaldo. |
| 500 | `Internal server error while serializing task parameters` | `ambiguous`, sin respaldo. |
| 500 | `Internal server error in moderation service` | `ambiguous`, sin respaldo. |
| 501 | `parameter store unavailable` | `ambiguous`, sin respaldo. |
| 505 | `moderation service timeout` | `ambiguous`, sin respaldo. |
| 503 | `System busy, please try again` | `ambiguous`, sin respaldo. |
| 500 | `resolution is not within the range of allowed options` | `validation`, respaldo permitido. |

**Las siete variantes internas terminan `failed/submission_ambiguous`: exactamente un POST KIE y cero POST a Higgsfield/APIMart.** La matriz directa con códigos 500, 501, 502, 503, 504, 505 y 599, y mensajes internos que mencionan parámetros o moderación, confirma `retryable=False` y `fallback_safe=False`.

El control del rechazo conocido conserva `validation` y provoca un único envío al respaldo Higgsfield, dentro del presupuesto. Ese control verifica la transición y el envío, no una generación remota completada.

También repetí las dos reproducciones originales con APIMart como respaldo disponible: tanto `Internal Server Error` como `invalid response from upstream` dejan **un envío KIE y ninguno a otros proveedores**. Los mensajes internos son casos sintéticos de prueba, no nuevas respuestas observadas en producción.

## Regresiones del flujo acumulado

- **Tarifas y proveedor más barato:** APIMart sube de 0,71 a 1,50 USD dentro del TTL; el primer envío automático cambia a KIE por 1,025 USD. Si se fuerza APIMart con techo 0,71 USD, no envía. Las cotizaciones locales se revisan antes del POST.
- **Lotes y presets:** cambios de precio devuelven 409 antes de crear el trabajo correspondiente. Un lote con techo numérico y aceptación de desconocido devuelve **422 `conflicting_approval`, cero trabajos y cero envíos**. La aceptación sin techo conserva `max_usd=None`, también cuando la tarifa aparece antes de crear y sube después.
- **Aprobación:** el 409 guarda el precio actualizado, sin conceder el permiso de la petición rechazada. La secuencia 409 → aprobación conocida con aceptación falsa → pérdida de tarifa termina **`awaiting_approval`, cero KIE**. Una aprobación desconocida con techo 0,71 USD bloquea después un precio conocido de 2,50 USD.
- **Retenciones:** el plan y la respuesta conservan `reserve_usd=4.9248` y `kind=approx`. La retención se exige con costo desconocido y en lotes incompletos; el MCP conserva lo visto y una subida de reserva devuelve 409. Mantener aprobaciones separadas para precio final y retención resulta aceptable con estas comprobaciones.
- **Ambigüedad en los tres adaptadores:** HTTP 503, cuerpos ilegibles/malformados y respuesta sin ID permanecen ambiguos, sin reintento ni respaldo.
- **Concurrencia y deduplicación:** aprobaciones simultáneas dan 200/409; cancelación ganadora conserva `canceled`. Un resultado de sondeo obsoleto pierde el CAS y no duplica respaldo. Proveedores forzados distintos crean trabajos distintos; repetir el mismo recupera el existente y cambiarlo con la misma clave devuelve 409. La carrera de limpieza de quotes MCP mantiene el techo autorizado.
- **Medios y SSRF:** MPD nuevo rechazado con 415. Fuente MPD anterior en voz y aislamiento: descarga únicamente el manifiesto y devuelve 422, sin petición al recurso interno. ffprobe real rechaza DASH por whitelist; MP4 válido mide 1,0 s. Descargas simultáneas usan temporales distintos.
- **Traducciones:** seed explícita sin equivalente y bitrate explícito no representable siguen como `unsupported`; APIMart conserva las semillas de los controles que sí soporta. KIE no vuelve a ofrecer Seedance edit/extend.
- **Webhooks y UI/MCP:** revisados token, proveedor, correlación y consulta autoritativa, transmisión de topes, aprobación de desconocido, actualización tras 409 y visualización de retención. Higgsfield conserva el almacén de medios y el contrato común sigue en `providers/base.py` y `registry.py`.

La comprobación de UI fue de código y cuerpos de API, sin automatización de navegador. No repetí F0 ni otras pruebas reales con créditos. El veredicto se refiere al código revisado y a las reproducciones simuladas, no a certificar respuestas futuras de los proveedores.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **336 passed, 2 skipped**.
- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducciones propias con las tablas de `tests/fixtures/prices_*.json`, escenarios adversariales en memoria y copia exacta de HEAD.

## Veredicto

**APROBADO.** El hallazgo de la ronda 35 está corregido y las reproducciones anteriores mantienen sus protecciones.

**Lista exacta de correcciones pendientes de esta revisión: ninguna.**
