---
name: videoclip
description: >-
  Planea un video musical (actuación, narrativa, concepto o híbrido) a partir de una canción, con tomas sincronizadas a sus secciones y su tempo. Úsala cuando el usuario quiera un videoclip, un visualizer o imágenes para una canción.
---

# Videoclip

## 1. Escucha la estructura
Pide la canción (adjunta) o sus datos: BPM, duración, secciones con tiempos (intro, verso, pre, estribillo,
puente, outro) y letra. Calcula: 1 compás de 4/4 = 240 / BPM segundos. Las tomas duran múltiplos de compás;
los cortes caen en el tiempo fuerte o, a propósito, a contratiempo.

## 2. Concepto (ask_user)
- Actuación: el artista canta o toca; barato, necesita variedad de planos.
- Narrativa: una historia paralela a la letra.
- Concepto: imágenes simbólicas del ánimo de la canción, no literal.
- Híbrido (lo más común): actuación en estribillos, narrativa o concepto en versos.
Parte del ánimo de la canción, no de un argumento.

## 3. Mapa de secciones
Por sección: qué se ve, energía, paleta, movimiento y tempo de corte. Versos: calm/dynamic, planos más
largos. Estribillos: dynamic/chaotic, más cortes, la imagen más fuerte. Puente: cambio de paleta o de lugar.
Que el color script siga la canción.

## 4. Consistencia del artista
El artista es un elemento con hoja de personaje y vestuario por look. Repite los locks en cada toma.
Si hay playback (labios), usa un modelo que acepte audio de entrada y pasa el tramo exacto de audio;
si no, evita planos donde los labios deban sincronizar.

## 5. Propuesta
Guarda las tomas por sección con `upsert_shots` (la escena es la sección) y propón tarjetas por sección
con `items` y su `shot_id`, clips de 4-10 s, mismo aspect ratio. Después, montaje en orden y mezcla
con la canción completa (hf-studio/combine y hf-studio/mix).
