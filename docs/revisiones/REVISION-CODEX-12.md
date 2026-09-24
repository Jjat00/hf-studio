# Revisión adversarial de `0d9869b`

Fecha: 2026-09-24. Alcance: el canje atómico de `voice_quote` solicitado en [REVISION-CODEX-11.md](REVISION-CODEX-11.md), incluidas las salidas por error, cancelación e idempotencia. No se hicieron llamadas de pago.

## Hallazgos

**Sin hallazgos bloqueantes. La carrera de la ronda 11 está resuelta.** `src/hf_studio/api.py:807-822` valida y marca la cotización como usada sin ningún `await` entre ambas operaciones. La validación del medio, el cupo y el guardado del trabajo ocurren después de la reserva (`:823-850`). Si fallan, `:867-870` la libera; tras un guardado correcto queda usada. El retorno por idempotencia previo a la reserva (`:793-804`) devuelve el trabajo existente sin iniciar otra conversión. Si una inserción simultánea con la misma clave encuentra ese trabajo, `:850-865` libera la cotización reservada por la petición que no creó nada.

Repetí la carrera con dos claves de idempotencia distintas y una barrera dentro de `probe_duration`: la primera petición mantuvo la reserva mientras la segunda intentó canjear el mismo `voice_quote`. Los estados fueron **202 y 409**, se creó un solo trabajo y ElevenLabs simulado recibió **una** llamada `speech-to-speech`. `tests/test_voice.py:264-274` también cubre dos envíos simultáneos.

No encontré una reserva bloqueada en las rutas revisadas. Una prueba temporal comprobó que `cost_changed` (409), cupo lleno (429) y cancelación de la petición antes del guardado dejan `used=False`; tras los dos errores, la misma cotización pudo crear un trabajo y quedó `used=True`. Un trabajo ya creado consume la cotización incluso si la conversión falla después, coherente con su uso único.

## Comprobaciones

1. Inspeccioné `git show HEAD` (`0d9869b`) y las rutas de retorno y excepción de `/v1/voice/changes`. Solo añadí este informe; no modifiqué código de la aplicación.
2. `.venv/bin/pytest -q`: **61 passed**. `.venv/bin/ruff check src tests`: **All checks passed**.
3. Tres pruebas adversariales temporales fuera del repo: canje concurrente, liberación tras errores previos al trabajo y liberación tras cancelación. **3 passed**; usaron ElevenLabs simulado.

## Veredicto

**APROBADO.** Una cotización ya no puede crear dos trabajos simultáneos en el proceso de API revisado, y las salidas anteriores a la creación liberan su reserva.
