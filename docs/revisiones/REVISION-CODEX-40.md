# Revisión adversarial de Codex, ronda 40

Fecha: 2026-10-03. HEAD **`af179e6`**. Revisados `git show HEAD`, las correcciones ES/EN de la landing y su correspondencia con el código y la documentación aprobada en la ronda 38.

**Sin llamadas de generación reales, sin gasto de créditos y sin modificar fuentes ni textos revisados.** La comprobación del CLI utiliza entrada, validación, escritura y navegador simulados. Este informe es el único archivo añadido; `tt.png` ya estaba sin seguimiento.

## Hallazgos

**No encontré hallazgos nuevos ni correcciones pendientes en el alcance revisado.**

## Correcciones verificadas

1. **Regla del agente:** `landing/src/lib/dict.ts:100` y `landing/src/lib/dict.ts:235` ya hablan de superar el **tope autorizado**, en lugar de cualquier subida. Leídas junto a la tarjeta que especifica recotización local siempre y TTL Higgsfield de 15 minutos, coinciden con `worker.refresh_quote` y `worker.within_budget`. El inicio mediante cotización y la espera de aprobación mantienen el sentido del flujo MCP; la documentación completa conserva los detalles de retención, desconocido y aprobación pendiente.
2. **Comandos de claves:** `landing/src/lib/dict.ts:61` y `landing/src/lib/dict.ts:196` distinguen correctamente `providers --open apimart`, que abre la página, de `--add apimart`, que pide, valida y guarda la clave. Repetí el control: `--add` da código 0, una escritura simulada y cero aperturas; `--open` da código 0 y una apertura simulada. Coincide con `cli._providers` y el README.

Las cifras y ejemplos permanecen correctos: **3 proveedores, 27 herramientas**, ahorro Seedance redondeado de **53 %**, Wan 2.7 a **0,332 USD en APIMart** y **0,40 USD en KIE** según rutas y fixtures. Los **0,425 USD de Higgsfield** siguen siendo el dato real aportado por Jaime en la ronda 39; su presentación a 0,43 USD es un redondeo correcto. No consulté de nuevo los proveedores.

## Validación

- En `landing/`, `pnpm lint` y `pnpm exec tsc --noEmit --incremental false`: **correctos**.
- Reproducción del CLI con efectos simulados: correcta.
- Recalculados precios de fixtures, ahorro y conteos del registro/MCP: correctos.
- El commit solo cambia cuatro textos de la landing y añade el informe anterior. No fue necesario repetir la suite completa, ffprobe ni pruebas manuales de navegador.

## Veredicto

**APROBADO.** Los dos hallazgos de la ronda 39 están corregidos en ambos idiomas.

**Lista exacta de correcciones pendientes de esta revisión: ninguna.**
