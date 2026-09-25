# Revisión adversarial de `275958f..ad8a7f8`

Fecha: 2026-09-24. Alcance: servicios de audio de ElevenLabs en API, MCP y UI, más reproducción, filtros y reutilización de generaciones. No se hicieron llamadas de generación a ElevenLabs ni a Higgsfield.

## Hallazgos

1. **[P1] La UI presenta un costo positivo como `$0.000`.** `src/hf_studio/elevenlabs_audio.py:125-129` cotiza texto a voz por carácter y conserva cuatro decimales. Por ejemplo, cuatro caracteres con `eleven_multilingual_v2` cuestan **$0.0004**. `web/src/lib/studio.ts:155-156` muestra solo tres decimales para importes menores de un centavo, así que tanto el panel (`web/src/components/studio/cost-panel.tsx:55-60`) como el botón (`web/src/components/audio/audio-studio.tsx:296-299`) muestran **~$0.000** antes de generar. La API exige una cotización válida, pero la persona no ve que esta operación tiene costo. Ajustar la precisión o expresar los importes positivos inferiores a $0.001 como un límite visible.

2. **[P2] «Aislar voz» no permite seleccionar un archivo de audio nuevo desde la UI.** El formulario promete «Video o audio», pero crea `MediaSlot` con `kind="video"` (`web/src/components/audio/audio-studio.tsx:276-278`); ese tipo fija `accept="video/mp4"` (`web/src/components/studio/media-slot.tsx:12-16,105-114`). La API sí admite WAV en `/v1/uploads` (`src/hf_studio/higgsfield.py:20-27`). Un WAV de una grabación local no aparece en el selector normal del navegador. Se puede aislar audio ya presente en la biblioteca o subir WAV por MCP/API, pero el flujo nuevo de la página queda incompleto.

3. **[P2] «Guardar como preset» se ofrece en audios que la API no admite como presets.** `web/src/components/generations/generation-card.tsx:181-185` muestra la acción para toda generación completada, incluidos los cuatro modelos nuevos. La ruta `/v1/presets/from-generation/{job_id}` delega en `check_preset`, que solo admite modelos del catálogo de Higgsfield (`src/hf_studio/api.py:611-615,646-668`), por lo que esos audios terminan en `404 unknown_model` después de pedir el nombre. Ocultar la acción para modelos locales o admitirlos explícitamente en presets.

## Comprobaciones

- Revisé el canje de `audio_quote` (`src/hf_studio/api.py:958-1067`): reserva sin `await` entre validación y marca de uso, libera antes de crear trabajo si hay error y conserva la clave de idempotencia para reintentos. El origen del aislamiento usa `trusted_media` o un trabajo propio; el worker de Higgsfield excluye los modelos locales. `run_audio_job` aplica un plazo y `voice._run` mata el subproceso al cancelarse.
- Contrasté tarifas y límites con [precios oficiales de ElevenLabs](https://elevenlabs.io/pricing/api), [modelos de texto a voz](https://elevenlabs.io/docs/overview/models), [API de efectos](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert), [API de música](https://elevenlabs.io/docs/api-reference/music/compose) y [aislamiento](https://elevenlabs.io/docs/overview/capabilities/voice-isolator). Las tarifas configuradas y los rangos principales coinciden con esas fuentes a la fecha de la revisión.
- `.venv/bin/pytest -q`: **67 passed**. `.venv/bin/ruff check src tests`: **All checks passed**. En `web/`, `pnpm lint` y `npx tsc --noEmit`: **sin errores**. Las pruebas nuevas usan un transporte HTTP simulado; no prueban una generación real de ElevenLabs.
- Solo añadí este informe. No modifiqué código de la aplicación.

## Veredicto

**CAMBIOS REQUERIDOS.** El costo positivo mostrado como cero incumple la regla de costo visible antes de generar. También hay dos acciones de UI que fallan o bloquean flujos anunciados.
