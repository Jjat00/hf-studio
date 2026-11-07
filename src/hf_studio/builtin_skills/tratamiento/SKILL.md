---
name: tratamiento
description: >-
  Escribe el tratamiento de director de un proyecto (logline, historia, tono, referencias, enfoque visual y sonoro, personajes, formato) y lo convierte en el brief del proyecto. Úsala al inicio de cualquier corto, anuncio, videoclip o serie, o cuando el usuario tenga una idea vaga y quiera "aterrizarla".
---

# Tratamiento de director

El tratamiento es la visión del director antes de rodar: qué se cuenta, cómo se siente y cómo se ve.
Aquí evita gastar en tomas sin rumbo.

## Preguntas (modo ask, una a la vez con ask_user)
Formato y duración (y aspect ratio), público y objetivo, tono (2-3 adjetivos), referencias que le gustan,
personajes o producto. Si el usuario dice "decide tú", decide y marca lo elegido.

## Estructura (Markdown, 400-900 palabras)
1. Logline: una frase (quién, qué quiere, qué lo impide).
2. Historia en beats: inicio, giro, clímax, cierre. Para piezas cortas, 3-6 beats con su duración.
3. Tono y emoción: qué debe sentir el público y cómo cambia beat a beat (es la base del color script).
4. Enfoque visual: género, era, cuerpo de cámara, lente, apertura dominante, filosofía de movimiento
   (p. ej. "cámara quieta que solo se mueve cuando el personaje pierde el control"), luz y paleta.
   Traduce cada decisión al parámetro de Cinema Studio (lee `lista-de-tomas/references/cinema-studio.md`).
5. Referencias: películas, fotógrafos o pintores, con qué tomar de cada uno. Si dudas de un dato, busca con
   web_search.
6. Personajes y lugares: una línea por elemento (nombre, función, rasgo visual clave).
7. Sonido: ambiente, música (género, tempo, instrumentación), diálogo o voz en off.
8. Formato y entregables: duración, ratio, plataformas.
9. Plan y presupuesto aproximado: número de tomas por modelo y coste estimado (usa find_models).

## Después
Guarda el tratamiento con `save_document` (kind `treatment`) y actualiza el brief con
`update_project_brief`, una sección cada vez (Narrativa, Visuales, Producción), con su resumen. Propón el siguiente paso: biblia de continuidad (si hay personajes) o lista de tomas.
No propongas generaciones dentro de esta skill salvo una prueba de look si el usuario la pide.
