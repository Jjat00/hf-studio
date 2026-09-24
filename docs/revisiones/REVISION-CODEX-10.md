# Revisión adversarial de `0ddb0b6`

Fecha: 2026-09-24. Alcance: las ocho correcciones solicitadas en [REVISION-CODEX-9.md](REVISION-CODEX-9.md) y las regresiones de este commit. No se hicieron llamadas de pago.

## Hallazgos

1. **SSRF: RESUELTO para URLs arbitrarias.** `src/hf_studio/api.py:705-719` y `src/hf_studio/service.py:45-58` aceptan como `source_url` solo una subida o salida registrada para el cliente; `src/hf_studio/service.py:73-83` aplica la misma regla a `keep_source_audio`. `tests/test_voice.py:179-183` verifica que una URL directa a metadatos internos se rechaza con 422 antes de abrir ffmpeg. La confianza en redirecciones y en el contenido servido por el proveedor sigue dependiendo de Higgsfield; no encontré una ruta demostrada para que un cliente registre una URL interna arbitraria.

2. **Video recortado por `keep_source_audio`: RESUELTO.** `src/hf_studio/audio.py:94-109` completa la pista con `apad`, limita la salida con `-shortest` y comprueba que su duración difiera menos de 0,1 s de la original antes de reemplazarla. `tests/test_audio.py:59-66` cubre un video de 4 s con audio de origen de 2 s.

3. **Idempotencia de voz: RESUELTO.** `src/hf_studio/api.py:779-792,820-833` compara la huella, devuelve 409 si cambió la petición y recupera una inserción simultánea con la misma clave. `web/src/components/voice/voice-studio.tsx:146-158` vincula la clave al cuerpo exacto. `tests/test_voice.py:166-176` cubre la reutilización indebida.

4. **Costo visible: PARCIAL, severidad ALTA.** El MCP toma los segundos de su `quote_id` (`src/hf_studio/mcp_server.py:214-221`) y la UI los envía desde la cotización visible (`web/src/components/voice/voice-studio.tsx:119-153`). La API vuelve a medir el tramo y rechaza cambios mayores a 0,05 s antes de crear el trabajo (`src/hf_studio/api.py:793-800`), con lo que cierra el caso de duración mutable en esos dos clientes. Sin embargo, `/v1/voice/changes` no exige una cotización emitida por el servidor: acepta `expected_seconds` declarado por el propio llamante (`src/hf_studio/api.py:773-780`). La prueba de extremo a extremo inicia una conversión simulada enviando solo ese número, sin llamar a `/v1/voice/estimate` (`tests/test_voice.py:108-119`). Un cliente directo puede gastar sin que exista evidencia de costo mostrado. **Arreglo propuesto:** canjear en la API un identificador de cotización ligado al dueño, petición y duración; mantener la comprobación de segundos como defensa adicional.

5. **Acceso global por el proxy web: PARCIAL, severidad MEDIA.** `dev.sh:13-15` liga Next a `127.0.0.1`, y `README.md:55-57` advierte sobre la falta de autenticación. Pero `web/src/app/api/studio/[...path]/route.ts:23-45` sigue poniendo la clave con `sees_all` en cualquier petición sin comprobar el visitante. `web/README.md:6-8` aún recomienda `pnpm dev` sin `--hostname`; `next dev --help` confirma que su valor por defecto es `0.0.0.0`. Ese camino vuelve a exponer las generaciones de todos los clientes en la red local. **Arreglo propuesto:** hacer seguro también el comando de `web/` (por ejemplo, fijar el host en el script) y exigir autenticación si se despliega fuera de la máquina.

6. **Audio convertido corto: PARCIAL, severidad ALTA.** `src/hf_studio/voice.py:249-273,305-306` mide la voz convertida y atenúa el original solo mientras aquella dura. `tests/test_voice.py:186-206` comprueba que vuelve el original cuando la voz nueva termina antes del tramo. Queda otro caso de duración: si el video de origen tiene imagen más larga que su pista de audio, `[dry]` acaba con el audio y `-shortest` corta la imagen (`src/hf_studio/voice.py:270-278`). Lo reproduje sin ElevenLabs: fuente de 4,000 s con audio de 2 s, voz convertida de 1 s; `mix_command` produjo un MP4 de 2,020 s y el trabajo se marcaría `completed`. **Arreglo propuesto:** completar la pista original hasta la duración de la imagen, fijar y verificar la duración final antes de publicar el resultado, y cubrir este caso en pruebas.

7. **Cupo y plazo de voz: PARCIAL, severidad MEDIA.** `src/hf_studio/api.py:801-809` impone `max_active_jobs_per_client` y `:845-852` añade un timeout. El reloj empieza *después* de adquirir uno de los dos puestos del semáforo, así que los trabajos en cola pueden esperar más que `job_timeout_seconds` y después ejecutarse. Además, el nuevo timeout cancela `change_voice` mientras `voice._run` espera un subproceso; `src/hf_studio/voice.py:202-212` mata el hijo solo al agotar su timeout interno, no al recibir cancelación. Lo reproduje con `sleep 5` y `asyncio.wait_for(..., 0.1)`: tras vencer el plazo, `child_alive_after_timeout: True`; lo maté en la prueba. **Arreglo propuesto:** medir el plazo desde la creación, incluso mientras espera el semáforo, y terminar y esperar cualquier subproceso en `CancelledError`.

8. **Filtro Video: RESUELTO.** `web/src/lib/studio.ts:3-9` define `outputOf` para el modelo local; `web/src/app/history/page.tsx:25-34` y `web/src/components/studio/studio.tsx:274` comparten el criterio. El cambio de voz aparece en el filtro Video.

## Comprobaciones

1. Inspeccioné `git show 0ddb0b6` y cotejé cada cambio con los ocho hallazgos de la ronda 9. No modifiqué código.
2. `.venv/bin/pytest -q`: **57 passed**. `.venv/bin/ruff check src tests`: **All checks passed**. En `web/`, `pnpm lint` y `npx tsc --noEmit`: **sin errores**.
3. Reproduje localmente la pérdida de duración de `mix_command` con ffmpeg y ffprobe: entrada 4,000 s, salida 2,020 s. Reproduje la supervivencia del subproceso tras cancelar `voice._run` y lo cerré al terminar la comprobación. No usé claves ni servicios de pago.
4. `pnpm exec next dev --help` indica `0.0.0.0` como host predeterminado; `dev.sh` sí lo sobreescribe con `127.0.0.1`.

## Veredicto

**CAMBIOS REQUERIDOS.** Cuatro hallazgos están resueltos y cuatro son parciales. La API aún acepta gasto sin una cotización verificable, el cambio de voz puede publicar un video recortado y el timeout puede dejar un proceso ffmpeg vivo.
