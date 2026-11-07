---
name: plan-de-cobertura
description: >-
  Planea la cobertura de una escena (plano maestro, planos individuales, OTS, insertos, cutaways, reacciones) respetando el eje de 180 grados, y la propone como tomas que montan entre sí. Úsala para diálogos, discusiones, escenas de mesa o acciones que se van a montar con varios ángulos.
---

# Plan de cobertura

La cobertura es el conjunto de ángulos de una misma escena que permite montarla. El maestro cubre toda
la acción; los planos más cerrados se intercalan. Un inserto reencuadra algo que ya está en el maestro;
un cutaway muestra algo que no está en él.

## Pasos
1. Geografía primero (ver skill `puesta-en-escena`): quién está a la izquierda de cuadro y quién a la
   derecha, hacia dónde mira cada uno. Esa es la línea de 180°: todas las tomas, del mismo lado.
2. Plan mínimo para diálogo de dos: Maestro (WS, f11-deep-focus, static-shot o dolly-in lento) + OTS de A sobre B +
   OTS de B sobre A + MCU/CU de A + MCU/CU de B + 1-2 insertos (manos, objeto) + 1 cutaway (ambiente).
   Acción: maestro + seguimiento (tracking/side-tracking) + POV + reacción + inserto de impacto.
3. Coherencia de ejes: si A mira a cámara-derecha en su CU, B mira a cámara-izquierda en el suyo. Escríbelo
   en cada prompt ("looking screen-right"). Mismo tamaño de plano para los dos lados del diálogo. La luz
   principal viene del mismo lado en todas las tomas.
4. Parámetros: misma escena, mismo género, luz, lente y paleta. Apertura: f11-deep-focus en el maestro,
   f4-moderate en OTS, f14-wide-open en primeros planos. Tempo: calm para diálogo, dynamic o chaotic para acción.
5. En la IA cada ángulo es una generación: propón la cobertura como UNA tarjeta con `items`, con las mismas
   referencias en el mismo orden, el fotograma del maestro como referencia de lugar y luz para los demás.
   Si el diálogo tiene audio, divide las líneas por toma y mantén la misma voz.
6. Guarda cada ángulo como toma con `upsert_shots` (misma escena, números consecutivos) y pasa su
   `shot_id` en cada item de la propuesta.
7. Presupuesto: calcula con `estimate_shot_list`; si es alto, ofrece una cobertura reducida (maestro +
   2 primeros planos + 1 inserto).

Romper el eje es válido solo si es intencional (desorientar, cambio de poder); dilo en la toma.
