---
name: lista-de-tomas
description: >-
  Convierte una escena, guion o idea de varios momentos en una lista de tomas numerada (plano, lente, movimiento, duración, elementos) y en su storyboard de fotogramas, y la propone como una sola tarjeta. Úsala cuando el usuario pida un corto, una secuencia, "varias tomas", un storyboard o una lista de tomas.
---

# Lista de tomas y storyboard

Tu entregable es una lista de tomas que se pueda generar tal cual y, antes del video, un storyboard barato
(una imagen por toma) para fijar encuadre y bloqueo. Corregir el bloqueo en el storyboard es casi gratis;
corregirlo en video obliga a regenerar.

## Flujo
1. Lee el brief del proyecto, `list_documents` (tratamiento, desglose, biblia), `get_shot_list` (no
   dupliques tomas que ya existen) y `list_elements`. Lee `references/cinema-studio.md` de esta skill
   con `read_skill_file`.
2. Divide en escenas (cambio de lugar o de tiempo) y cada escena en beats (un cambio de intención o de
   información). Un beat suele ser una toma. Orientación: 1 min de pieza son 8 a 15 tomas.
3. Para cada toma define: número (escena.toma, p. ej. 2.3), propósito en una frase (qué cuenta), tamaño de plano
   (EWS, WS, MS, MCU, CU, ECU, insert, OTS), ángulo y altura, movimiento (de la lista de 33), apertura, duración,
   elementos en cuadro, dirección de pantalla (quién mira o se mueve a izquierda o derecha), sonido clave,
   transición de salida (corte seco, match cut, whip).
4. Fija por escena, no por toma: género, era, tempo, cuerpo, lente, luz y paleta. Varía por toma solo plano,
   movimiento, apertura y duración.
5. Guarda la lista con `upsert_shots` (una entrada por toma, con `model_id`, `params`, `prompt` y
   `element_ids`): el usuario la ve en la vista Shot list del proyecto. Muestra en el chat solo un
   resumen breve y pregunta con `ask_user` si la aprueba o quiere cambios (en modo auto, sigue). Con
   `estimate_shot_list` da el presupuesto total antes de producir.
6. Storyboard: propone UNA tarjeta con `items` (una por toma) en un modelo de imagen con referencias. Mismo
   aspect ratio que el video, las imágenes de los elementos como referencia, prompt = encuadre + acción + luz.
   Cada item lleva su `shot_id` y `shot_role: "board"`: el fotograma queda como storyboard de esa toma.
7. Video: con los fotogramas aprobados, propone las tomas en Cinema Studio 4.0 (u otro modelo
   image-to-video o first-last-frame), con el fotograma como `<<<image_1>>>` y los elementos como siguientes
   referencias. Empieza por la toma más difícil de cada escena: si esa sale, el resto suele salir.
   Cada item lleva su `shot_id`: al generarse, la toma pasa a «generating» y luego a «review».
8. Si dos tomas son continuas (misma acción), encadénalas: el último fotograma de la toma N es la primera
   imagen de la N+1. Usa `chain_shot` con la toma N terminada y `to_shot_id` de la N+1: te da la URL del
   fotograma para pasarla como imagen inicial.

## Consistencia
Repite en cada prompt los mismos "locks": nombre del personaje, vestuario con colores concretos, peinado,
la misma fuente de luz y su lado. Usa siempre las mismas imágenes de referencia en el mismo orden.
Una toma de Cinema Studio puede contener un mini shot list con tiempos ("SHOT 1 · 0.0-3.0s · …") si el
tempo no es single-shot.
