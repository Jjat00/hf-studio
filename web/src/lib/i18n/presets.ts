import type { Locale } from ".";
import type { Preset } from "../types";

/**
 * Traducción al español de los presets de serie (la API los sirve en inglés porque también los usa el MCP).
 * Las opciones se traducen solo al mostrarlas: el valor enviado sigue siendo el inglés que entra en el prompt.
 * Los presets guardados por el usuario se muestran tal cual.
 */
type PresetEs = {
  title: string;
  description: string;
  labels?: Record<string, string>;
  placeholders?: Record<string, string>;
};

const PRESETS_ES: Record<string, PresetEs> = {
  "hero-shot": {
    title: "Foto hero de producto",
    description: "Packshot de estudio premium de tu producto, listo para una landing o un anuncio.",
    labels: { product: "Producto", surface: "Superficie", ratio: "Formato" },
    placeholders: { product: "auriculares inalámbricos negro mate" },
  },
  "reel-cover": {
    title: "Portada de reel",
    description: "Portada vertical 9:16 con espacio para un titular, en el estilo que elijas.",
    labels: { subject: "Tema", mood: "Ambiente" },
    placeholders: { subject: "un barista sirviendo arte latte" },
  },
  "cinematic-establishing": {
    title: "Plano de establecimiento cinematográfico",
    description: "Plano de apertura amplio de cualquier lugar, con movimiento de cámara y sonido ambiente.",
    labels: { place: "Lugar", move: "Cámara", resolution: "Calidad" },
    placeholders: { place: "un pueblo pesquero con niebla al amanecer" },
  },
  "photo-to-life": {
    title: "Dale vida a una foto",
    description: "Movimiento sutil y natural para un retrato o una foto fija: respiración, pelo, luz.",
    labels: { photo: "Foto", detail: "Qué debe moverse", resolution: "Calidad" },
    placeholders: { detail: "el pelo moviéndose con el viento, una sonrisa suave" },
  },
  morph: {
    title: "Transición entre dos fotogramas",
    description: "Una transición continua de una imagen a otra.",
    labels: { start: "Fotograma inicial", end: "Fotograma final", style: "Transición" },
  },
  "product-orbit": {
    title: "Órbita 360 de producto",
    description: "Órbita lenta alrededor de la foto de tu producto, como un plato giratorio publicitario.",
    labels: { photo: "Foto del producto", resolution: "Calidad" },
  },
  "dance-transfer": {
    title: "Transferir un baile",
    description: "Tu personaje hace los pasos de cualquier video de baile.",
    labels: { character: "Imagen del personaje", dance: "Video del baile (3–30 s)" },
  },
  "ad-multiplier": {
    title: "Multiplicador de anuncios",
    description: "Cambia el producto de un anuncio existente y conserva todo lo demás.",
    labels: { ad: "Anuncio original (4–30 s)", product: "Producto nuevo", note: "Qué reemplazar" },
    placeholders: { note: "reemplaza la botella de su mano" },
  },
  "character-in-scene": {
    title: "Personaje en una escena nueva",
    description: "Pon a los personajes de tus imágenes de referencia en un plano nuevo.",
    labels: { refs: "Referencias del personaje", scene: "Escena" },
    placeholders: { scene: "caminando por un mercado de neón de noche, cámara en mano" },
  },
};

/** Opciones de los selectores de presets: valor en inglés (entra en el prompt) → texto en español. */
const OPTIONS_ES: Record<string, string> = {
  "polished concrete": "cemento pulido",
  "white marble": "mármol blanco",
  "dark wood": "madera oscura",
  "reflective glass": "vidrio reflectante",
  "bold and colorful": "atrevido y colorido",
  "moody cinematic": "cinematográfico y sombrío",
  "clean minimal": "limpio y minimalista",
  "retro film": "película retro",
  "slow aerial push-in": "acercamiento aéreo lento",
  "lateral tracking shot": "travelling lateral",
  "crane up reveal": "grúa que asciende y revela",
  "static wide with drifting clouds": "plano amplio fijo con nubes",
  "smooth morph": "fusión suave",
  "camera push through": "la cámara atraviesa",
  "light burst": "destello de luz",
  "liquid transformation": "transformación líquida",
};

const CATEGORY_ES: Record<string, string> = {
  Product: "Producto",
  Social: "Redes",
  Cinematic: "Cine",
  Animate: "Animar",
  Motion: "Movimiento",
};

export function localizePreset(p: Preset, locale: Locale): Preset {
  const es = locale === "es" && p.builtin ? PRESETS_ES[p.slug] : undefined;
  if (!es) return p;
  return {
    ...p,
    title: es.title,
    description: es.description,
    variables: p.variables.map((v) => ({
      ...v,
      label: es.labels?.[v.key] ?? v.label,
      placeholder: es.placeholders?.[v.key] ?? v.placeholder,
    })),
  };
}

export function presetOption(value: string, locale: Locale) {
  return locale === "es" ? (OPTIONS_ES[value] ?? value) : value;
}

export function presetCategory(category: string, locale: Locale) {
  return locale === "es" ? (CATEGORY_ES[category] ?? category) : category;
}
