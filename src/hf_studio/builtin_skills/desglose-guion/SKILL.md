---
name: desglose-guion
description: >-
  Desglosa un guion o texto en escenas y elementos de producción (personajes, extras, lugares, props, vestuario, efectos, sonido, VFX) y decide cuáles se crean como elementos. Úsala cuando el usuario pegue o adjunte un guion, escaleta o relato para producirlo.
---

# Desglose de guion

En producción se marca cada elemento del guion por categoría (reparto, extras, props, vestuario,
decorado, efectos, sonido) para saber qué hay que conseguir. Aquí sirve para saber qué elementos crear,
qué referencias faltan y cuánto costará.

## Pasos
1. Numera las escenas. Por escena: encabezado (INT/EXT, lugar, DÍA/NOCHE), resumen en una línea,
   duración estimada en pantalla (1 página de guion ≈ 1 minuto; en piezas IA, cuenta beats).
2. Por escena, extrae en tabla:
   - Reparto (con nombre) y extras.
   - Lugar y momento del día.
   - Props que se tocan o importan a la trama.
   - Vestuario y estado (mojado, herido, sucio).
   - Efectos y VFX (lluvia, fuego, criatura, pantalla).
   - Sonido clave (diálogo, efectos, música).
   - Dificultad para un modelo: alta si hay más de 2 personajes con diálogo, multitud, manos con objetos
     pequeños, texto en pantalla, acción física compleja.
3. Agrupa: lista única de elementos con las escenas donde aparecen. Todo lo que aparezca en 2 o más
   escenas es candidato a elemento (ver `list_elements`); lo que aparece una vez va descrito en el prompt.
4. Señala riesgos y simplificaciones: escenas imposibles o caras para la IA y cómo resolverlas (cambiar
   a plano detalle, sacar personajes de cuadro, dividir en tomas).
5. Guarda el desglose con `save_document` (kind `breakdown`; si el usuario pegó el guion, guárdalo
   también con kind `script`). Pregunta con ask_user por dónde seguir:
   biblia de continuidad (crear elementos) o lista de tomas de la escena 1.

No inventes escenas ni personajes que el guion no tenga; si algo es ambiguo, pregúntalo.
