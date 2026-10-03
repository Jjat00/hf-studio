# Revisión adversarial de Codex, ronda 37

Fecha: 2026-10-03. HEAD **`0822f4f`**. Alcance: documentación del último commit, `README.md`, `README.es.md` y `AGENTS.md`, contrastada con código, fixtures y resultados de las rondas 28 a 36.

Solo lectura de fuentes, ayuda de CLI, pruebas y reproducciones con `httpx.MockTransport`, claves falsas y bases temporales. **Sin llamadas de generación reales, sin gasto de créditos y sin modificar código ni la documentación revisada.** Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. MEDIA: la sección nueva promete recotización antes de cada envío sin explicar la reutilización de cotizaciones Higgsfield

**Ubicación:** `README.md:54`, `README.es.md:37`. Evidencia: `src/hf_studio/worker.py:321`, `src/hf_studio/worker.py:327`, `src/hf_studio/routing.py:79`.

**Afirmación:** «Before sending, the price is quoted again» / «Antes de enviar se vuelve a cotizar», seguida de la promesa de aprobación ante un precio mayor.

**Escenario concreto:** crear una generación forzada a Higgsfield con cotización de 1,51 USD y techo 1,51 USD. Cambiar la respuesta del cotizador simulado a 3 USD antes del envío. Si la opción tiene menos de 15 minutos, el worker hace **un POST de generación y cero POST a `/estimate`**, conserva el costo de 1,51 USD y queda `queued`. Con la misma opción envejecida 901 segundos, hace **un POST a `/estimate`, cero envíos** y queda `awaiting_approval` con 3 USD.

Esto demuestra que la garantía documental es más fuerte que el comportamiento. El primer envío automático normal rehace el plan, pero una opción Higgsfield forzada, de respaldo o aceptada como desconocida puede reutilizar su cotización dentro del TTL. Las tablas locales de APIMart/KIE sí se recalculan siempre antes de enviar. Esta diferencia estaba expresamente aceptada y documentada en las revisiones anteriores; no es una regresión nueva del código.

Además, «un precio mayor necesita aprobación» debe referirse al **tope aprobado**, no a cualquier subida frente al precio anterior. Si el usuario aceptó esa opción con costo desconocido y sin techo, una tarifa que aparece o sube después puede enviarse sin otra aprobación; con techo numérico, este manda cuando el precio se conoce. La retención conserva su aprobación independiente en ambos casos.

**Arreglo sugerido:** ajustar ambos idiomas para describir la recotización local siempre, el TTL de 15 minutos de Higgsfield y el replan inicial automático. Expresar que se vuelve a pedir aprobación cuando la cotización comprobada supera el techo autorizado, el costo se vuelve desconocido sin permiso para esa opción o la retención supera lo autorizado. Explicar la excepción explícita de costo desconocido sin techo. No cambiar código para resolver esta ronda documental.

### 2. MEDIA: la guía MCP conserva un contrato universal de `quote_id` que contradice la nueva aprobación, y omite las dos herramientas nuevas

**Ubicación:** `AGENTS.md:37`, `README.md:193`, `README.md:206`, `README.es.md:204`, `README.es.md:217`; badges en `README.md:7` y `README.es.md:7`. Evidencia: `src/hf_studio/mcp_server.py:504`.

**Escenario concreto:** el nuevo párrafo de AGENTS manda usar `approve_fallback`, pero inmediatamente después establece que **toda herramienta de pago exige `quote_id`**. `approve_fallback` lleva el título «spends credits» y no acepta ese parámetro. Su firma recibe `generation_id`, `max_usd`, `max_reserve_usd` y `accept_unknown_cost`; autoriza la opción pendiente y la API recotiza al aprobar. Un agente que siga la regla universal puede intentar conseguir o pasar un `quote_id` que esta herramienta no usa, o confundir `confirm_unknown_cost` de generación con `accept_unknown_cost` de aprobación.

Comprobé la llamada con el cliente REST sustituido por un recolector: `approve_fallback('job', max_usd=1.025, max_reserve_usd=4.9)` envía esos importes y `accept_unknown_cost=False`, **sin `quote_id`**. No envía ninguna petición real.

Los README siguen anunciando y enumerando **25 herramientas**; el código registra **27**, incluyendo `approve_fallback` y `providers_status`, ambas ausentes de las tablas. La descripción de cotización no explica el mecanismo distinto de aprobación ni su retención y aceptación de desconocido.

**Arreglo sugerido:** limitar la exigencia de `quote_id` a las herramientas de generación inicial que lo utilizan y explicar la aprobación del trabajo pendiente como mecanismo separado. Documentar los tres campos de aprobación, el permiso explícito para precio desconocido, el comportamiento con/sin techo y la conservación de la aprobación de retención. Añadir las dos herramientas a las tablas y actualizar los conteos y badges en ambos idiomas.

## Afirmaciones comprobadas

- **Claves:** `HF_API_KEY`, `APIMART_API_KEY`, `KIE_API_KEY` y `ELEVENLABS_API_KEY` coinciden con `.env.example`, configuración y registro. Higgsfield sigue siendo el requisito del setup y el almacén de medios de entrada.
- **Comandos:** `providers --add NAME`, `providers --open NAME`, `start --api-only`, `setup --no-input` y los comandos de conexión existen. `providers --help` confirma sus opciones. La validación de proveedores usa comprobaciones de clave/saldo, sin generación; el CLI guarda en `.env` y la UI presenta los enlaces.
- **Ejemplo de precios:** Seedance 2.0, 720p, 5 s: APIMart `0.142 × 5 = 0.71` USD; KIE `0.205 × 5 = 1.025` USD. Higgsfield 1,51 USD coincide con el cotizador simulado de `tests/test_routing.py`, que reproduce el ejemplo utilizado en las revisiones. No volví a verificar precios de mercado en vivo.
- **Ruteo y semántica:** selección por costo entre opciones compatibles/configuradas, proveedor forzado, mapas del mismo modelo y exclusión de ajustes explícitos sin equivalente. Los ejemplos de seed y bitrate siguen cubiertos por pruebas.
- **Respaldo:** solo tras rechazo seguro o fallo reembolsado, sujeto a presupuesto y retención aprobados. Los envíos ambiguos no se reintentan ni pasan a otro proveedor. El arreglo KIE de la ronda 36 sigue en HEAD.
- **Retenciones:** precio final y retención se autorizan por separado; una opción puede necesitar aprobación aunque sea más barata si requiere una retención no autorizada.
- **Extensión:** el registro alimenta setup, CLI, API, worker y MCP; la UI recibe datos del registro y tiene presentación genérica para proveedores nuevos. Las claves adicionales no requieren un campo específico en `Settings`.
- **Requisitos y comprobaciones:** Python 3.12+ coincide con `pyproject.toml`; la UI usa Next.js 16; CI cubre Windows/macOS/Linux. No ejecuté comandos de instalación, registro, apertura de navegador o escritura de claves.

## Validación

- `uv run hf-studio providers --help`: opciones documentadas correctas.
- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q tests/test_routing.py tests/test_routes.py tests/test_setup.py tests/test_mcp_cost.py`: **171 passed**.
- Reproducción independiente del TTL Higgsfield, inspección de firma/cuerpo de aprobación MCP y conteo de las 27 herramientas por AST.
- El commit solo cambia documentación; no fue necesario repetir ffprobe, la suite completa ni las comprobaciones de UI que pasaron en la ronda 36.

## Veredicto

**NO APROBADO**, por documentación. Falta exactamente:

1. Corregir en ambos README la garantía de recotización y aprobación: TTL Higgsfield, techo autorizado, excepción explícita de desconocido sin techo y retención independiente.
2. Corregir el contrato MCP en AGENTS y ambos README: aprobación sin `quote_id`, campos de aprobación conocidos/desconocidos y retención; añadir `approve_fallback` y `providers_status` y actualizar los conteos a 27.

El veredicto del código multiproveedor de la ronda 36 permanece **APROBADO**. Esta revisión no requiere cambios de implementación.
