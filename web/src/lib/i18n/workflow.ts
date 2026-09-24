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
  [/edit images/gi, "editar imágenes"],
  [/create character/gi, "crear personaje"],
  [/generate and edit/gi, "generar y editar"],
  [/^generate$/gi, "generar"],
  [/ fast$/gi, " rápido"],
];

export function workflowLabel(workflow: string, locale: Locale) {
  if (locale === "en" || !workflow) return workflow;
  const out = WORKFLOW_ES.reduce((acc, [re, to]) => acc.replace(re, to), workflow);
  return out.charAt(0).toUpperCase() + out.slice(1);
}
