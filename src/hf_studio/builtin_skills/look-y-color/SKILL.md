---
name: look-y-color
description: >-
  Define el look del proyecto (lookbook con referencias, cámara, lente, luz, paleta) y su color script (cómo cambia el color con la emoción escena a escena), con fotogramas de prueba baratos. Úsala antes de una serie de tomas, cuando el usuario hable de estética, mood board, look o paleta, o quiera "que todo se vea igual".
---

# Look y color script

Un lookbook es el plano visual que fija el tono para todo el equipo. Un color script es la secuencia de
paletas que sigue la emoción de la historia (Pixar lo hace para cada película: colores apagados en los
momentos oscuros, saturados en los felices).

## Lookbook
1. Reúne referencias: adjuntos del usuario, frames de películas o fotografía (busca con web_search si nombra
   obras concretas). Para cada referencia, di qué se toma de ella (luz, color, encuadre, textura).
2. Decide y documenta: género, era, camera_model, camera_lens, apertura dominante, 1-2 esquemas de luz,
   paleta principal con 3-5 colores nombrados (hex aproximados) y texturas (grano, halación).
3. Prueba de look: propone UNA tarjeta con `variations` 3-4 o `items` (una por paleta o lente candidata) del
   mismo encuadre representativo, en el modelo más barato que acepte esos parámetros (o una imagen) y a 480p si
   es video. Pide al usuario que elija.

## Color script
1. Toma los beats del tratamiento y asigna a cada uno emoción + temperatura (cálido/frío) + saturación +
   contraste + paleta de Cinema Studio + esquema de luz. Ejemplo: "Encuentro: esperanza, cálido,
   contre-jour, gasoline-sunset → Pérdida: tristeza, frío desaturado, window, the-grey-channel".
2. El cambio de color marca el arco: no cambies de paleta dentro de una escena salvo que la escena sea el giro.
3. Opcional: una tarjeta con `items` de un fotograma clave por beat, para verlo como tira.

Guarda lookbook y color script con `save_document` (kinds `lookbook` y `color_script`) y resume con
`update_project_brief` en la sección Visuales (paleta, lente, luz y sus valores de parámetro), que es lo
que leerán las demás skills. Los valores de parámetro están en `lista-de-tomas/references/cinema-studio.md`
(léelo con `read_skill_file` name "lista-de-tomas").
