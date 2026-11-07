---
name: revision-dailies
description: >-
  Revisa las generaciones terminadas como si fueran dailies (encuadre, actuación, continuidad, artefactos, ritmo), elige la toma buena, da notas concretas y propone solo las regeneraciones necesarias. Úsala cuando lleguen resultados, el usuario pregunte "¿qué tal quedó?" o diga que algo no le gusta.
---

# Revisión de dailies y notas

Los dailies son lo rodado del día; el director los revisa, marca las tomas buenas y da notas.
Aquí cada generación es una toma.

## Revisión (por toma)
Mira la imagen o los fotogramas con `review_generation` (para video, 4 a 8 fotogramas con su tiempo; con
`compare_with` añade los elementos o la toma vecina aprobada) y compara con la toma planificada
(`get_shot_list`). Puntúa 1-5 y anota:
1. Historia: ¿se entiende el beat? ¿llega la emoción?
2. Encuadre y cámara: plano, movimiento y primer/último fotograma pedidos.
3. Actuación y movimiento: gestos naturales, manos, física, velocidad.
4. Continuidad: cara, vestuario, props, luz y su lado, dirección de pantalla y miradas frente a la
   biblia y las tomas vecinas.
5. Técnica: artefactos, deformaciones, texto roto, parpadeo, saltos.
6. Sonido (si hay): sincronía, voz correcta, ambiente.
Veredicto: Aprobada / Aprobada con nota (se arregla en montaje) / Repetir.

## Notas que sirven
- Específicas y accionables: "a los 3 s la mano izquierda atraviesa la taza; acortar a 4 s y pasar la taza a
  la derecha" en vez de "se ve rara".
- Separa notas de estructura (orden, ritmo, falta una toma) de notas de pulido (color, un artefacto).
- Agrupa por tema y resuelve contradicciones antes de proponer cambios.

## Qué cambiar al repetir
Cambia una sola cosa por intento y di cuál: prompt (restricción concreta), referencia (mejor fotograma,
otra hoja), parámetro (apertura, movimiento más simple, duración menor) o modelo. Si falla dos veces,
simplifica la toma (menos personajes, plano más cerrado). Usa variaciones solo cuando el problema sea
de azar, no de instrucción.

Registra el veredicto con `update_shot`: `verdict` y `notes`, `status` approved o retake y, si se
aprueba, `selected_job_id` con la toma buena. Al cerrar una escena, propone el montaje con las tomas
aprobadas en orden (`hf-studio/combine` con sus URLs).
