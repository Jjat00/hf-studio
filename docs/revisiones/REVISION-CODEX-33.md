# Revisión adversarial de Codex, ronda 33

Fecha: 2026-10-03. Rama `feat/multiproveedor`, HEAD **`8feb9bb`**. Revisados `git show HEAD`, el diff contra `aa0e721` y sus efectos en creación, aprobación, lotes, presets, worker, MCP y UI. Las reproducciones propias se ejecutaron sobre una copia de `git archive 8feb9bb` en `/tmp/hf-review33-8feb9bb`.

Proveedores simulados con `httpx.MockTransport`, claves falsas y SQLite/almacenamiento temporales. Para medios utilicé ffprobe/ffmpeg reales y HTTPS en loopback. No hice generaciones reales, no gasté créditos y no modifiqué código. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. ALTA: aceptar desconocidos en un lote elimina también un techo total numérico explícito

**Ubicación:** `src/hf_studio/api.py:755`, `src/hf_studio/api.py:780`, `src/hf_studio/api.py:785`, `src/hf_studio/worker.py:287`.

**Escenario:** el endpoint acepta combinar `accept_unknown_cost=true` con un `max_total_usd` finito. Comprueba ese techo al crear, pero luego asigna `max_usd=None` a todos los Jobs por el flag, sin considerar que la petición sí tenía un límite total. Además, marca la primera opción de cada Job con `unknown_accepted=True`. Cuando una tabla cambia antes del envío, el worker permite cualquier precio conocido para esa opción, porque el techo ya desapareció de la persistencia.

Es una regresión de la nueva rama de lotes. La aceptación sin techo funciona cuando `max_total_usd=None`; la misma autorización no puede inferirse cuando el cliente envió un valor numérico. En generación y `/approve`, la regla corregida establece precisamente que el techo numérico manda cuando el precio se conoce.

**Reproducción:** crear un lote de un único Seedance 2.0, 720p, 5 s, con el siguiente cuerpo:

```json
{
  "items": [{
    "model": "bytedance/seedance-2.0/text-to-video",
    "input": {
      "prompt": "A paper boat sailing down a rainy street",
      "resolution": "720p",
      "duration": 5,
      "aspect_ratio": "9:16"
    }
  }],
  "max_total_usd": 0.71,
  "accept_unknown_cost": true
}
```

La tarifa inicial APIMart es **0,71 USD**, así que REST responde **202**. Sin embargo, el Job ya publica **`max_usd=None`**. Cambiar `seedance-2.0|720P` a **0,30 USD/s** y ejecutar `worker.submit`: recotiza a **1,50 USD**, hace **un POST simulado a APIMart** y deja el trabajo **`queued`**. Para un lote de un solo Job, el envío supera inequívocamente el techo total de **0,71 USD**. No hay `awaiting_approval` ni nuevo consentimiento.

**Controles:** con el mismo techo y `accept_unknown_cost=false`, el Job conserva 0,71 USD y no se envía tras el aumento; queda esperando aprobación. Con `accept_unknown_cost=true` y `max_total_usd=None`, queda sin techo y envía a 1,50 USD, que sí corresponde a la modalidad explícitamente ilimitada. El MCP actual envía `None` cuando acepta un total incompleto; el fallo demostrado está en la combinación que REST permite a otros clientes.

**Arreglo sugerido:** distinguir lote sin techo de lote con techo numérico al persistir los Jobs. Si existe `max_total_usd`, conservar y hacer cumplir el presupuesto en los envíos y respaldos, mediante presupuestos por Job cuya suma no exceda el total o una autorización compartida del lote. Si se decide que `accept_unknown_cost` en lotes solo puede significar autorización ilimitada, rechazar su combinación con un techo numérico antes de crear trabajos. No aceptar el techo al entrar y descartarlo después. Añadir el caso de un ítem y otro con varios ítems/copias y cambios de tarifas, manteniendo independiente la retención aprobada.

## Repetición de los dos hallazgos de la ronda 32

| Caso | Resultado en `8feb9bb` |
| --- | --- |
| 409 → aprobación conocida con aceptación falsa → pérdida de tarifa | KIE espera a 1,025 USD. Aprobar 1 USD con aceptación desconocida devuelve 409; la fila conserva **`unknown_accepted=False`**. Aprobar 1,025 con aceptación explícita falsa devuelve 200. Vaciar luego la tarifa deja **`awaiting_approval`, `usd=None`, cero envíos KIE**. El permiso rechazado ya no aparece y la aprobación válida guarda False. |
| Quote desconocido → tarifa conocida al crear → aumento posterior, generación | El propio MCP produce `max_usd=None` y aceptación verdadera. Restaurar APIMart a 0,71 antes de crear conserva **`max_usd=None` y `unknown_accepted=True`**. Subir después a 1,50 genera **un envío simulado**, estado `queued`, como corresponde a esa opción autorizada sin techo. |
| Misma transición en preset | Dry-run desconocido; tarifa restaurada antes del POST confirmado; el Job conserva **`max_usd=None`**. El aumento posterior a 1,50 produce **un envío APIMart**, sin la aprobación adicional incorrecta anterior. |

## Comprobaciones de regresión adicionales

- **Techos ordinarios:** aceptar un desconocido con techo de 0,71 USD en generación sigue bloqueando la tarifa conocida de 1,50, con cero envíos. El defecto de este informe se limita a la persistencia del techo total en lotes con el flag.
- **Alcance de aceptación:** la opción aceptada sin techo no concede permiso al respaldo. Tras el rechazo seguro de Higgsfield y paso a APIMart desconocido, queda `awaiting_approval`, sin envío al respaldo.
- **Retenciones:** el MCP mantiene 4,9248 USD de reserva vista en un lote de total incompleto. Al subir a 9,8496, REST devuelve **409 `reserve_not_approved`**, sin envío. Un techo final ausente no permite omitir la aprobación de una retención nueva.
- **MCP y presets UI:** la aceptación explícita sigue llegando a REST; `approve_fallback` sin techo obtiene 200 y un envío simulado al proveedor aprobado. Inspección de la conexión de UI y reproducción de sus cuerpos, sin automatizar navegador.
- **Deduplicación:** proveedores forzados distintos crean Jobs distintos; repetir el mismo forzado o selección automática devuelve su Job existente. Una misma `Idempotency-Key` con otro proveedor forzado devuelve 409. No se ejecutó una nueva prueba F0 real.
- **Proveedor más barato:** con techo de 2 USD y APIMart actualizado de 0,71 a 1,50, el replan envía a **KIE por 1,025 USD**, cero APIMart. Forzar APIMart conserva esa elección.
- **Envíos ambiguos:** 503 y respuesta APIMart malformada terminan `failed/submission_ambiguous`, un envío y cero KIE. No se reintentan ni generan respaldo automático.
- **Carreras:** dos aprobaciones producen 200/409. Cancelación que gana conserva `canceled` y rechaza aprobar. La limpieza concurrente de quotes MCP conserva `max_usd=0.71`.
- **Medios:** dos descargas concurrentes de la misma URL terminan correctamente. El MPD nuevo devuelve 415; voz y aislamiento con una subida anterior descargan solo el manifiesto fuente y responden 422, sin GET interno. ffprobe real lo rechaza por whitelist y un MP4 válido mide 1,0 s.

No encontré otro problema nuevo de doble envío, fuga de claves o SSRF en los caminos revisados. La excepción de costo desconocido sin techo permanece limitada a la opción aceptada; las reservas siguen requiriendo aprobación independiente.

## Validación

- `UV_CACHE_DIR=/tmp/hf-review28-uv uv run pytest -q`: **326 passed, 2 skipped**.
- `uv run ruff check src tests`: **All checks passed**.
- En `web/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducciones con la copia exacta de `8feb9bb`, tablas de `tests/fixtures/prices_*.json`, bases temporales y modificaciones de objetos en memoria. No se modificaron las fuentes del repositorio ni se llamaron endpoints pagados reales.

## Veredicto

**NO APROBADO.** Falta exactamente:

1. Evitar que `accept_unknown_cost=true` elimine un `max_total_usd` numérico en lotes: conservar y hacer cumplir el presupuesto total antes de los envíos, o rechazar explícitamente esa combinación antes de crear trabajos. La modalidad sin techo debe seguir usando un total explícitamente ausente y mantener la aprobación independiente de retenciones.
