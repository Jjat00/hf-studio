# Revisión adversarial de Codex, ronda 39

Fecha: 2026-10-03. HEAD **`1ed83f5`**. Revisados `git show HEAD`, los textos ES/EN y la sección nueva de `landing/`, contrastados con el código y la documentación aprobada en la ronda 38.

**Sin llamadas de generación reales, sin gasto de créditos y sin modificar código ni textos de la landing.** Reproducciones con proveedores simulados, claves falsas y bases temporales; comprobación del CLI con entrada, validación, escritura y navegador sustituidos en memoria. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

### 1. MEDIA: la regla del agente vuelve a prometer otro OK ante cualquier subida de precio

**Ubicación:** `landing/src/lib/dict.ts:100` y `landing/src/lib/dict.ts:235`.

**Afirmación:** «si el precio sube, el agente vuelve a pedirte el OK» / «if the price goes up the agent asks for your OK again».

**Escenario concreto:** generación forzada a Higgsfield, cotización reciente de 1,51 USD y techo 1,51 USD; el cotizador simulado pasa a 3 USD antes de enviar. Repetí la reproducción de la ronda 37: **cero consultas nuevas a `/estimate`, un POST de generación, estado `queued`**, sin otra aprobación. Envejeciendo la cotización 901 segundos, el control sí recotiza y queda `awaiting_approval` con 3 USD, cero envíos.

El texto de proveedores de esta misma landing describe correctamente el TTL de 15 minutos, pero la regla del agente promete una detección/aprobación universal que el sistema no ofrece. Además, lo que manda es el techo autorizado, no cualquier aumento frente al precio previo; una opción aceptada con precio desconocido y sin techo puede enviarse al precio que acabe teniendo, con la retención todavía exigida por separado. `worker.within_budget` y los README aprobados explican esas condiciones.

**Arreglo sugerido:** en ambos idiomas, decir que las ejecuciones iniciales de pago requieren la cotización y que el agente solicita aprobación cuando el sistema detecta que la opción supera el precio o la retención autorizados, o se vuelve desconocida sin permiso. Evitar «cualquier subida». Mantener la limitación de recotización Higgsfield y la excepción explícita de desconocido sin techo; puede enlazarse al README para el detalle. La aprobación de una ejecución pendiente es el paso separado `approve_fallback`, sin otro `quote_id`.

Este es un desajuste de la promesa de la landing, no una regresión del código aprobado en la ronda 36.

### 2. BAJA: `providers --add apimart` no abre el enlace

**Ubicación:** `landing/src/lib/dict.ts:61` y `landing/src/lib/dict.ts:196`. Evidencia: `src/hf_studio/cli.py:163`, `src/hf_studio/cli.py:168`, `src/hf_studio/setup.py:254`.

**Escenario concreto:** ambos textos dicen que `hf-studio providers --add apimart` «abre el enlace» / «opens the link». Ese comando imprime las URLs, pide la clave, la comprueba y la guarda. La llamada a `webbrowser.open` existe únicamente en la rama `--open NAME`.

Reproducción sin efectos reales: `--add apimart` termina con código 0, **una escritura simulada y cero aperturas de navegador**; `--open apimart` termina con código 0 y **una apertura simulada**. El usuario que sigue la instrucción espera una pestaña que nunca aparece.

**Arreglo sugerido:** cambiar el texto a «muestra los enlaces y pide, valida y guarda la clave», o presentar `--open apimart` como el comando separado que abre la página, igual que los README aprobados. No requiere cambiar el CLI.

## Comprobaciones correctas

- **Cifras:** el registro contiene Higgsfield, APIMart y KIE: 3 proveedores de generación. El AST del servidor registra 27 herramientas MCP; ambos idiomas muestran 27.
- **Seedance:** 0,71 / 1,025 / 1,51 USD coinciden con el ejemplo aprobado. El ahorro `round((1 - 0.71 / 1.51) × 100)` es **53 %**. La comparación muestra fecha y conserva tres decimales cuando hacen falta.
- **Wan 2.7:** las rutas y fixtures calculan **0,332 USD en APIMart** y **0,40 USD en KIE** para texto a video, 5 s, 720p. Los **0,425 USD de Higgsfield** son el dato de la cotización real aportado por Jaime; no repetí esa consulta. Los textos 0,33 / 0,43 son redondeos a centavos correctos, no tarifas exactas nuevas. Que KIE no aparezca en la frase breve del ejemplo no altera cuál es el más barato.
- **Modelo y configuración:** la sección coincide con la exclusión de proveedores que no representan ajustes explícitos. La elección de precio se entiende entre opciones compatibles y configuradas, como explica el cuerpo de la sección.
- **Recotización en la tarjeta:** APIMart/KIE antes de enviar y Higgsfield cuando la cotización supera 15 minutos: correcto. El defecto está en la regla absoluta del agente, no en esa tarjeta.
- **Respaldo:** describe fallo sin cobro y comparación con lo aprobado; el código también exige reserva autorizada y bloquea envíos ambiguos.
- **Requisitos:** Higgsfield obligatorio para setup/medios; APIMart/KIE opcionales. Python, Node/pnpm y ffmpeg concuerdan con la documentación del producto. La sección de audio mantiene ElevenLabs como opcional.
- **Integración de la sección:** enlace `#proveedores`, ID correspondiente y componente incluido en la página. ES/EN tienen la misma estructura. No hice automatización de navegador ni pruebas manuales de producto.

## Validación

- En `landing/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Cálculo con las rutas reales y `tests/fixtures/prices_*.json`: precios Wan y ahorro Seedance correctos.
- Reproducciones independientes del TTL Higgsfield y del comportamiento `--add` frente a `--open`: resultados anteriores confirmados, sin peticiones o escrituras reales de claves.
- El commit no cambia backend; no fue necesario repetir la suite completa o ffprobe.

## Veredicto

**NO APROBADO**, por textos de la landing. Falta exactamente:

1. Corregir la regla del agente en ES/EN para no prometer aprobación ante cualquier subida: respetar comprobación/TTL, topes, retención y aceptación explícita de desconocido; distinguir inicio de ejecución y aprobación pendiente.
2. Corregir en ES/EN la descripción de `providers --add`: no abre el enlace; esa acción corresponde a `--open`.

Los veredictos aprobados del código multiproveedor y de la documentación de la ronda 38 permanecen vigentes. No se requieren cambios de backend.
