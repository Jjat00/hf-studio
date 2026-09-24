# Revisión adversarial de `1758f6a`

Fecha: 2026-09-24. Alcance: los cuatro hallazgos parciales de [REVISION-CODEX-10.md](REVISION-CODEX-10.md) y regresiones introducidas por este commit. No se hicieron llamadas de pago.

## Hallazgos

1. **Costo con cotización del servidor: PARCIAL, severidad ALTA.** La API ahora emite un `voice_quote` ligado al cliente, a la huella de la petición y a los segundos calculados (`src/hf_studio/api.py:760-774`), y lo exige antes de crear el trabajo (`:784-828`). El MCP y la UI lo reenvían (`src/hf_studio/mcp_server.py:214-221`, `web/src/components/voice/voice-studio.tsx:148-160`). **Queda una carrera que permite gastar dos veces con una sola cotización:** la API comprueba `quote["used"]` antes de `await voice_plan(...)`, pero solo lo marca usado después del `await session.commit()` (`src/hf_studio/api.py:805-860`). Reproduje dos solicitudes simultáneas con el mismo `voice_quote` y claves de idempotencia distintas, sincronizadas dentro de `probe_duration`: ambas devolvieron 202, crearon IDs diferentes y la API simulada de ElevenLabs recibió dos llamadas `speech-to-speech`. **Arreglo propuesto:** reservar o canjear el quote de forma atómica antes de cualquier `await` posterior a la validación; si se falla antes de crear el trabajo, liberar la reserva de forma segura. Añadir una prueba de dos canjes simultáneos con claves distintas.

2. **Proxy de la UI expuesto: RESUELTO para los comandos documentados.** `web/package.json:5-8` fija `--hostname 127.0.0.1` tanto en `pnpm dev` como en `pnpm start`; `dev.sh:13-15` usa el primero y `web/README.md:6-13` explica que el proxy no autentica y que no debe exponerse sin autenticación. El proxy sigue confiando en quien alcance Next, así que un despliegue que cambie el host o abra un túnel necesita la protección indicada.

3. **Imagen recortada en el cambio de voz: RESUELTO.** `src/hf_studio/voice.py:287-305` completa el audio original con silencio y fija la salida a la duración de la pista de video. `:334-345` mide la imagen resultante y rechaza la mezcla si difiere más de 0,1 s. `tests/test_voice.py:233-248` cubre una fuente con 4 s de imagen y 2 s de audio.

4. **Plazo y subprocesos: RESUELTO para las rutas revisadas.** `src/hf_studio/api.py:870-888` pone `asyncio.wait_for` alrededor de la espera del semáforo y de toda la conversión. `src/hf_studio/voice.py:202-216` y `src/hf_studio/audio.py:49-63` matan y esperan el subproceso al recibir `CancelledError`. `tests/test_voice.py:250-261` verifica que el hijo no siga vivo tras cancelar la tarea.

## Comprobaciones

1. Inspeccioné `git show HEAD` (`1758f6a`) y cotejé cada cambio con la ronda 10. Solo añadí este informe; no modifiqué código de la aplicación.
2. `.venv/bin/pytest -q`: **60 passed**. `.venv/bin/ruff check src tests`: **All checks passed**. En `web/`, `pnpm lint` y `npx tsc --noEmit`: **sin errores**.
3. Prueba adversarial temporal, fuera del repo, con el `voice_env` y ElevenLabs simulado: forcé que dos peticiones pasaran la comprobación del mismo quote antes de seguir. Resultado: estados `[202, 202]`, dos IDs y **dos llamadas** `speech-to-speech`. No hubo gasto real.

## Veredicto

**CAMBIOS REQUERIDOS.** Tres hallazgos están resueltos. La cotización de voz sigue pudiendo financiar dos trabajos simultáneos, contra la regla de un solo uso.
