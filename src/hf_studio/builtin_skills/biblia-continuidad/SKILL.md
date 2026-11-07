---
name: biblia-continuidad
description: >-
  Crea y mantiene la biblia de continuidad del proyecto (personajes, lugares, props con hojas de referencia, rasgos fijos y vestuario por escena) y la aplica en cada toma. Úsala al empezar un proyecto con personajes recurrentes, cuando una cara o vestuario "deriva" entre tomas, o antes de una serie de tomas.
---

# Biblia de continuidad

En cine, la persona de continuidad (script supervisor) vigila vestuario, maquillaje, luz, ejes y
miradas entre tomas. Aquí ese papel es tuyo: la consistencia no la garantiza el modelo, la garantizan
referencias fijas y descripciones repetidas.

## 1. Inventario
Lista personajes, lugares y props recurrentes (del desglose o del brief). Revisa `list_elements`: no
dupliques lo que ya existe.

## 2. Referencias por elemento
- Personaje: hoja de personaje (usa la skill `character-sheet`): cuerpo completo y rostro de frente,
  fondo neutro. Para Kling 3.0 hacen falta 2 a 4 imágenes; añade un 3/4 y un perfil si hay presupuesto.
- Lugar: un plano general establecido con la luz de la escena y, si hay tiempo, un contraplano.
- Prop o producto: frente y 3/4 sobre fondo neutro.
Propón todas las hojas en una tarjeta con `items`. Cuando el usuario apruebe una, conviértela en elemento
con `create_element_from_generation` (sale una tarjeta que el usuario confirma; los elementos se comparten
en todo el estudio y el nombre es único).

## 3. Ficha escrita (va al documento "Biblia" del proyecto: `save_document` con kind `bible`)
Por elemento: nombre (@nombre), rasgos invariables (edad, complexión, tono de piel, pelo, ojos, marcas),
vestuario por escena (con colores concretos), objetos que lleva, cómo se mueve y cómo habla, emoción
dominante por acto, voz (si hay audio). Por lugar: hora del día, fuente de luz principal y su lado, paleta,
objetos fijos y su posición.

## 4. Aplicación en cada toma
- Mismas imágenes, mismo orden de referencias en todas las tomas de la escena.
- Una frase de "locks" en cada prompt: "@Ana: same face, same short black bob, same mustard raincoat".
- Estado de continuidad: si en la escena 3 se moja o se mancha, anótalo y arrástralo a las tomas siguientes.
- Prefiere el mejor fotograma ya aprobado de la escena como referencia extra frente a la hoja original:
  reduce la deriva.
- Si una toma deriva (otra cara, otro abrigo), no la arregles con más texto: corrige la referencia
  y regenera solo esa toma. Para comprobarlo, `review_generation` con `compare_with` = los ids de los
  elementos o de la toma aprobada vecina.
