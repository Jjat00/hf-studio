---
name: spot-publicitario
description: >-
  Planea y propone un anuncio de 6, 15 o 30 segundos (gancho, problema, producto como héroe, prueba, cierre con marca y CTA) con producto consistente. Úsala cuando el usuario pida un comercial, spot, anuncio en video o pieza de marca (no UGC: para UGC usa la skill de UGC si existe).
---

# Spot publicitario

## Estructura por duración
- 6 s (bumper): 1 idea. 0-2 s gancho visual con el producto, 2-5 s beneficio en acción, 5-6 s marca.
- 15 s: 0-2 gancho, 2-6 problema o deseo, 6-11 producto en uso (héroe), 11-15 cierre: logo, claim, CTA.
- 30 s: 0-3 gancho, 3-8 problema visible, 8-14 entra el producto, 14-24 demostración y prueba (2-3 tomas),
  24-30 hero shot + cierre de marca con espacio negativo para el CTA.
El producto debe verse antes de la mitad. Cada toma tiene un solo trabajo y muestra acción, no intención.

## Pasos
1. Pregunta (ask_user, una a una): plataforma y ratio, objetivo (venta, marca, lanzamiento), producto
   (elemento existente o fotos), tono.
2. Producto como elemento: si no existe, créalo con 2-4 fotos limpias. Cítalo en cada toma y repite sus
   rasgos (color, material, logo, forma). No dejes que el modelo escriba el logo: el cierre con logo y texto
   se compone aparte o se hace con un modelo de imagen fuerte en texto.
3. Look de publicidad: camera_model modern, camera_lens clean-sharp, f11-deep-focus para producto entero y
   f14-wide-open para detalles, luz soft-cross o window, paletas limpias (static-noon, breakfast-on-schedule) salvo que la marca
   pida otra cosa. Tempo dynamic. Movimientos: robot-arm, slider, dolly-in, arc para producto; tracking para
   personas.
4. Guarda los beats como tomas con `upsert_shots` y da el presupuesto con `estimate_shot_list`.
   Storyboard: una tarjeta con `items` (un fotograma por beat, cada uno con su `shot_id` y
   `shot_role: "board"`) antes del video.
5. Video: 1 generación de 15 s con shot list interno con tiempos o una por beat si se van a encadenar
   (`chain_shot` para el fotograma y `hf-studio/combine` para unirlas). Sonido: música con tempo del ritmo de corte y SFX en los cortes.
6. Ofrece versiones por plataforma con la skill `entregables-plataforma`.
