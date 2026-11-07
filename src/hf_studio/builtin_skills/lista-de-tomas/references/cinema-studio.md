# Mapa de decisiones de dirección a Cinema Studio 4.0 (higgsfield/cinema-studio/4.0)

Orden: género primero (condiciona todo lo demás), después era, tempo, cuerpo, lente, apertura, luz, paleta y movimiento.
Un parámetro omitido lo elige el modelo; "auto" no es un valor válido.
Fija género, luz, lente y paleta POR ESCENA, no por toma: cambiarlos dentro de una escena rompe la unidad visual.

- genre: epic (escala, héroe), drama (personas, diálogo), noir (crimen, sombra), comedy, horror, action.
- era: 1960s/1980s/1990s/2000s/2020s. Ajusta grano, color y estilo de lente de época.
- pacing: calm (contemplativo, diálogo), dynamic (publicidad, acción legible), chaotic (pelea, pánico),
  single-shot (plano secuencia: nunca pidas cortes en el prompt con este valor).
- camera_model: modern (limpio, publicidad), 35mm-film (cine), 8mm-film (recuerdo, flashback, casero),
  dv-camcorder (found footage, 2000s, documental crudo).
- camera_lens: clean-sharp (producto, tech), anamorphic (épico, 21:9, flares), vintage-anamorphic (70s/80s),
  warm-vintage (nostalgia, romance), halation-vintage (sueño, neón, glow).
- camera_aperture: f14-wide-open (aislar rostro: primeros planos, emoción), f4-moderate (planos medios,
  dos personajes), f11-deep-focus (planos generales, geografía, producto entero).
- light: silhouette (misterio, final), practicals (lámparas en cuadro: noir, interiores nocturnos), window
  (drama íntimo, día), overhead-fall (interrogatorio, opresión), contre-jour (contraluz: romance, épico),
  soft-cross (diálogo bien modelado, publicidad de belleza).
- camera_movement por intención:
  revelar = crane-up, aerial-pullback, tilt-up, pedestal-up | acercarse a la emoción = dolly-in, slow-zoom-in |
  aislar o despedir = dolly-out, slow-zoom-out | vértigo o shock = dolly-zoom, crush-zoom |
  seguir = tracking, side-tracking, truck-left, truck-right, slider-left, slider-right |
  barrer o descubrir de lado = pan-left, pan-right | inmersión = pov, handheld, snorricam |
  energía = whip-pan, bullet-time, robot-arm | escala = drone-orbit, helicopter-shot |
  cambiar de foco narrativo = rack-focus | contemplar = static-shot | rodear = arc-left, arc-right |
  bajar = crane-down, tilt-down, pedestal-down.
- color_palette (agrupación orientativa por nombre: confirma con una prueba barata antes de fijarla):
  noche urbana/noir: neon-rain-at-midnight, after-dark, the-investigation, the-grey-channel, industrial-fog, the-iron-borough
  cálida/nostalgia: oil-ochre, gasoline-sunset, runaway-summer, amber-wasteland, the-faded-fresco, field-post
  romance/pop: pink-velvet, wallpaper-romance, back-row-kissing-seats, bubblegum-boulevard, the-crimson-ballet
  terror/tensión: the-earth-keeps-things-reluctantly, crimson-vigi, dont-turn-it-off-im-watching,
                 everyone-speaks-in-whispers, the-neighbors-saw-everything
  ciencia ficción/sueño: ghost-in-the-code, bioluminescent-night, on-the-other-side-of-the-porthole, a-dream-in-color
  luz de día limpia/publicidad: static-noon, breakfast-on-schedule, the-morning-after-rain, mirage-at-noon
  tropical/cálida saturada: tropic-fever-dream, turquoise-mirage, favela-gold

Referencias: una imagen fija identidad y vestuario y otra fija locación y luz. Cítalas por orden con <<<image_N>>>
y repite en texto lo que no puede cambiar ("the same woman in the same red coat in every shot").
Emoción: Cinema Studio en la app tiene una rueda de emociones por personaje (hope, anger, joy, trust, fear, surprise,
sadness, disgust); por API escríbela en el prompt junto al personaje.
