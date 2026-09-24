# Revisión adversarial de `f5ea4a5`

Fecha: 2026-09-24. Alcance: las tres correcciones pedidas en [REVISION-CODEX-7.md](REVISION-CODEX-7.md) y sus posibles regresiones en `web/`.

## Hallazgos

No encontré hallazgos bloqueantes en este commit.

## Comprobaciones

1. **Aviso en descripciones externas:** `web/src/components/studio/controls.tsx:34-37,121-150` usa `t.controls.externalHint()` solo para el placeholder. El diccionario español antepone «Higgsfield, en inglés:» y el inglés deja la descripción original (`web/src/lib/i18n/dictionaries.ts:93,416`). Comprobé el caso de `negative_prompt` de Qwen Image 3: el resultado español queda identificado y el texto no entra en `onChange` ni en la entrada enviada a la API. Los campos sin descripción conservan su comportamiento previo.

2. **Nombre de `file_url`:** `web/src/lib/i18n/dictionaries.ts:110` lo presenta como «Archivo de referencia» en español. Comparé las 62 claves de `input_schema.properties` de los 82 modelos actuales con `controls.fields` y `media.labels`: no queda ninguna sin etiqueta española, aparte de `prompt`, que tiene su etiqueta propia. `file_url` sigue siendo la clave enviada a la API.

3. **Errores propios del proxy:** `web/src/app/api/studio/[...path]/route.ts:10-19,23-25,29-33,53-56` elige el mensaje con `hfs-lang` y español por defecto. Probé el servidor Next 16 construido para esta revisión contra una API local inaccesible: `api_down` respondió 502 en español sin cookie y con `es`, y en inglés con `en`. Probé también `HF_STUDIO_TOKEN` vacío: `misconfigured` respondió 500 con los mismos idiomas. El código de error, el estado HTTP y la ruta de proxy conservaron su comportamiento.

4. **Regresiones:** `pnpm build` y `pnpm lint` pasaron con Next 16.2.11. El diff no modifica `i18n-provider.tsx`, las rutas `?prompt=` y `?reuse=`, el cálculo de costo ni el envío de presets o generaciones. No hice una prueba manual de producto ni una generación de pago.

## Veredicto

**APROBADO.** Los tres hallazgos de la ronda 7 están resueltos para el catálogo y los flujos actuales. No queda trabajo requerido por esta revisión.
