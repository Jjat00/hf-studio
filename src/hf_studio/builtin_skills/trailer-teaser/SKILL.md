---
name: trailer-teaser
description: >-
  Estructura y propone un tráiler (60-150 s) o teaser (15-60 s) de un proyecto o idea: tres actos de intensidad creciente, título y un button final. Úsala cuando el usuario pida un tráiler, teaser, avance o promo de una historia.
---

# Tráiler y teaser

## Estructura
- Tráiler (3 actos): Acto 1 (25 %) mundo y protagonista, cortes lentos, tono. Acto 2 (45 %) conflicto
  y escalada: el ritmo de corte se acelera hasta un pico. Acto 3 (20 %) montaje rápido de momentos
  clave y silencio o golpe antes del título. Título (5 %). Button (5 %): un último instante de humor,
  susto o giro después del título; suele ser lo que más se recuerda.
- Teaser: un solo gancho, revela poco. Imagen intrigante → 2-4 destellos → título → button.

## Pasos
1. Si hay proyecto, parte del tratamiento y la biblia; no reveles el final.
2. Lista de tomas con duración por toma: 2-4 s en acto 1, 1-2 s en acto 2, 0,5-1 s en acto 3. Muchas tomas
   cortas: genera clips de 4-5 s y recórtalos en el montaje.
3. Look: el de la película (mismo género, lente, paleta). Para tomas espectaculares: crane-up, aerial-pullback,
   dolly-zoom, bullet-time, anamorphic. Tempo dynamic o chaotic en el acto 2-3.
4. Tarjetas de texto ("ESTE VERANO…") y título: créalas aparte (imagen con texto) o déjalas para el montaje.
5. Sonido: música en tres partes (subida, pico, silencio) y un impacto (braam, hit) en los cortes clave.
   Busca primero en la sonoteca.
6. Guarda las tomas con `upsert_shots`, propón los clips en una tarjeta con `items` (cada uno con su
   `shot_id`) y, cuando estén, el montaje en orden (`hf-studio/combine`).
