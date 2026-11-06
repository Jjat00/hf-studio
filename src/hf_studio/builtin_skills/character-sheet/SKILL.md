---
name: character-sheet
description: Crea la hoja de personaje (character sheet) de un personaje a partir de una imagen o de una descripción en texto. Es una sola imagen horizontal con el cuerpo completo sin la cabeza, el rostro de frente y los detalles (manos, calzado, accesorios, telas, marcas). Úsala cuando el usuario pida un character sheet, una hoja de personaje, la ficha visual de un personaje o un personaje consistente para usar después en videos.
---

# Character sheet

Tu entregable es UNA imagen horizontal que sirve de referencia del personaje para generar después imágenes y videos con la misma persona y el mismo vestuario. No es una ilustración bonita: es una ficha técnica limpia, legible y consistente.

## Composición (siempre igual)

Lienzo horizontal 16:9 (o 3:2 si el modelo no tiene 16:9), fondo de estudio liso gris claro (#E6E6E6), luz suave y uniforme de estudio, sin sombras duras ni decorado. Tres zonas, separadas por márgenes limpios:

1. **Cuerpo completo sin cabeza (izquierda, ~45 % del ancho):** el personaje de pie, de frente, en postura neutra y relajada (brazos ligeramente separados del cuerpo), encuadrado desde la base del cuello hasta los pies. La cabeza queda fuera del encuadre: el corte va justo por debajo de la barbilla. Se ve todo el vestuario, el calzado y la silueta, con los pies completos y apoyados.
2. **Rostro de frente (arriba a la derecha):** retrato de cabeza y hombros, mirando a cámara, expresión neutra, pelo y orejas visibles, misma luz. Es la única cara de la hoja.
3. **Detalles (abajo a la derecha, 3 o 4 recuadros):** primeros planos de lo que identifica al personaje: manos (uñas, anillos), calzado, accesorios (bolso, gafas, joyas), textura de la tela o estampado, tatuajes, cicatrices o marcas. Elige los que existan; no inventes accesorios.

Reglas de la hoja:
- Una sola persona, idéntica en todas las zonas: misma piel, mismo cuerpo, mismo vestuario y misma luz.
- Sin texto, etiquetas, flechas ni marcas de agua, salvo que el usuario pida rótulos (los modelos suelen escribirlos mal).
- Sin fondo narrativo, sin props que no lleve el personaje y sin poses dinámicas.
- Realismo fotográfico salvo que el usuario o la imagen de origen sean de otro estilo (ilustración, 3D, anime): en ese caso mantén ese estilo en las tres zonas.

## Flujo

1. **¿De dónde sale el personaje?**
   - **De una imagen** (adjunta o elegida del historial): esa persona es la referencia. Conserva su identidad (rasgos, tono de piel, pelo, complexión) y su vestuario tal cual, salvo lo que el usuario pida cambiar. Si en la imagen no se ve el cuerpo entero o falta el calzado, complétalo de forma coherente y díselo al usuario en una línea.
   - **De texto:** en modo Preguntar, aclara solo lo que falte y cambie el resultado, una pregunta a la vez y con opciones: quién es (edad aproximada, complexión, rasgos), vestuario y estilo (foto realista, ilustración, 3D). Si el usuario dice que decidas, decide tú.
2. **Formato:** 16:9 horizontal por defecto, sin preguntar (la hoja siempre es horizontal). Si el modelo lo permite, 2K.
3. **Modelo:** busca con `find_models` un modelo de imagen que respete bien la composición en paneles y la identidad.
   - Con imagen de origen: uno de edición o referencias de imagen (capacidades `edit` o `image-references`), con la imagen en su campo de imágenes.
   - Desde texto: uno de texto a imagen.
   - Lee su esquema con `get_model` antes de proponer.
4. **Prompt (en inglés),** con esta estructura y adaptado al personaje:

```
Character reference sheet, horizontal 16:9 layout on a plain light gray studio background (#E6E6E6), soft even studio lighting, clean margins between panels.
LEFT PANEL (about 45% of the width): full-body front view of [the person from image 1 | description], standing straight in a neutral relaxed pose, arms slightly away from the body, framed from the base of the neck down to the feet. The head is cropped out of the frame just below the chin. Entire outfit and shoes visible, feet fully in frame.
TOP RIGHT PANEL: frontal head-and-shoulders portrait of the same person, looking straight at the camera, neutral expression, hair and ears visible, same lighting.
BOTTOM RIGHT: [3-4] close-up detail panels of [hands with rings | shoes | bag | fabric texture | tattoo on the forearm].
The same person, outfit and lighting in every panel. [Outfit: …]. [Style: realistic photo with natural skin texture | illustration style of the reference].
No text, no labels, no watermark, no extra people, no background scenery.
```

5. **Resumen y propuesta:** resume lo decidido (origen, personaje, vestuario, estilo, formato, modelo) y propón con `propose_generation`.

## Después de generar

- Si la cara del panel no coincide con la persona de origen, o el panel izquierdo muestra la cabeza, propone otra versión reforzando esa parte del prompt («the head is cropped out of the frame», «exactly the same face as image 1»).
- Ofrece los siguientes pasos: usar la hoja como referencia de imagen en un video (modelos con `image-references` o `reference-to-video`), o guardarla como elemento en la página Elementos para citarla con @nombre en Kling 3.0. Un elemento necesita de 2 a 4 imágenes: sugiere la hoja y un recorte del rostro.
