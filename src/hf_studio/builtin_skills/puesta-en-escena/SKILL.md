---
name: puesta-en-escena
description: >-
  Define la geografía y el bloqueo de una escena (posiciones, recorridos, entradas y salidas, eje de 180 grados, dirección de pantalla, posiciones de cámara) antes de las tomas. Úsala en escenas con dos o más personajes, persecuciones, entradas y salidas o cuando las tomas "no casan" entre sí.
---

# Puesta en escena y bloqueo

## 1. Plano de planta (en texto)
Describe el espacio visto desde arriba como una lista: dimensiones aproximadas, puertas y ventanas
(y por dónde entra la luz), muebles fijos, dónde está cada personaje al empezar y al terminar, sus
recorridos con flechas ("A: puerta → mesa"), y las posiciones de cámara numeradas (C1 maestro desde el
sur, C2 OTS sobre A...). Todas las cámaras al mismo lado del eje de acción.

## 2. Reglas de continuidad espacial
- Dirección de pantalla: si alguien sale por la derecha de cuadro, entra por la izquierda en la toma
  siguiente. Un viaje de A a B mantiene la misma dirección (izquierda a derecha = avanzar).
- Miradas: en un diálogo, uno mira a cuadro derecha y el otro a cuadro izquierda.
- Luz: la fuente principal (ventana, lámpara) está en el mismo lado relativo en todas las tomas.
- Cruce del eje solo intencional, con una toma puente (movimiento de cámara que cruza a la vista,
  plano neutro de frente o un personaje que cruza).

## 3. Traducción a prompts
En cada toma escribe posición y dirección explícitas: "Ana stands frame-left by the window, facing
screen-right toward Leo; window light from frame-left". Para que un movimiento de cámara sea coherente,
dilo respecto a algo del espacio ("dolly-in toward Ana from the doorway").
Usa como referencia de lugar el mismo fotograma establecedor en todas las tomas.

## 4. Verificación
Opcional y barato: propone una imagen de planta cenital (top-down blueprint, sin texto) o un fotograma
del maestro con todos en posición, y úsalo como referencia. Guarda el bloqueo con `save_document` (kind `blocking`, un documento por escena).
