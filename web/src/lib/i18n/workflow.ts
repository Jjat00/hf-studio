import type { Locale } from ".";

/** Nombres de flujo del catálogo de Higgsfield («Pro · Text to video») en español; los nombres propios se quedan. */
const WORKFLOW_ES: [RegExp, string][] = [
  [/text to video/gi, "texto a video"],
  [/image to video/gi, "imagen a video"],
  [/text to image/gi, "texto a imagen"],
  [/reference to video/gi, "referencias a video"],
  [/first last frame/gi, "fotograma inicial y final"],
  [/video edit/gi, "editar video"],
  [/video extend/gi, "extender video"],
  [/video reference/gi, "referencia de video"],
  [/image reference/gi, "referencia de imagen"],
  [/motion transfer/gi, "transferir movimiento"],
  [/object swap/gi, "cambiar objetos"],
  [/^restyle$/gi, "cambiar estilo"],
  [/generate ads/gi, "generar anuncios"],
  [/edit images/gi, "editar imágenes"],
  [/create character/gi, "crear personaje"],
  [/generate and edit/gi, "generar y editar"],
  // Flujos de los modelos de tienda (APIMart, KIE).
  [/animate move/gi, "animar con movimiento"],
  [/animate replace/gi, "reemplazar personaje"],
  [/character edit/gi, "editar personaje"],
  [/character remix/gi, "remezclar personaje"],
  [/character scene/gi, "personaje en escena"],
  [/edit with mask/gi, "editar con máscara"],
  [/edit video/gi, "editar video"],
  [/extend video/gi, "extender video"],
  [/image to image/gi, "imagen a imagen"],
  [/^remix$/gi, "remezclar"],
  [/remove background/gi, "quitar fondo"],
  [/speech to video/gi, "voz a video"],
  [/talking video/gi, "video hablando"],
  [/upscale video/gi, "escalar video"],
  [/^upscale$/gi, "escalar"],
  [/^generate$/gi, "generar"],
  [/ fast$/gi, " rápido"],
];

export function workflowLabel(workflow: string, locale: Locale) {
  if (locale === "en" || !workflow) return workflow;
  const out = WORKFLOW_ES.reduce((acc, [re, to]) => acc.replace(re, to), workflow);
  return out.charAt(0).toUpperCase() + out.slice(1);
}

const fold = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{Diacritic}/gu, "");

/** ¿Coincide la búsqueda con el id, el título original o el flujo tal como se muestra en este idioma? */
/** `extra`: más texto en el que buscar (p. ej. el nombre traducido de una herramienta de HF Studio). */
export function matchesModel(m: { id: string; title: string }, query: string, locale: Locale, extra = "") {
  if (!query) return true;
  const workflow = m.title.replace(/ API$/, "").split(" — ")[1] ?? "";
  return fold(`${m.id} ${m.title} ${workflowLabel(workflow, locale)} ${extra}`).includes(fold(query));
}
