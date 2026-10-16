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
    title: "Plano de apertura cinematográfico",
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
  relight: {
    title: "Reiluminar",
    description: "Cambia la luz de una foto (dirección, color y ambiente) sin tocar al sujeto.",
    labels: { photo: "Foto", light: "Luz" },
  },
  "color-palette": {
    title: "Cambiar paleta de color",
    description: "Vuelve a etalonar una foto con otra paleta y otro ambiente sin cambiar lo que hay en ella.",
    labels: { photo: "Foto", palette: "Paleta" },
  },
  "face-swap": {
    title: "Cambio de cara",
    description: "Pon la cara de una foto en otra, con la luz, el ángulo y el tono de piel igualados.",
    labels: { photo: "Foto de destino", face: "Cara a usar", ratio: "Formato" },
  },
  "character-swap": {
    title: "Cambio de personaje",
    description: "Sustituye a la persona de una escena por tu personaje y conserva pose, lugar y luz.",
    labels: { scene: "Escena", character: "Tu personaje", ratio: "Formato" },
  },
  "reframe-image": {
    title: "Reencuadrar imagen",
    description: "Cambia el formato de una foto extendiéndola con naturalidad más allá de sus bordes.",
    labels: { photo: "Foto", ratio: "Formato nuevo" },
  },
  "video-relight": {
    title: "Reiluminar video",
    description: "Cambia la iluminación de un clip y conserva su movimiento.",
    labels: { video: "Video", light: "Luz" },
  },
  "video-color-grade": {
    title: "Etalonar video",
    description: "Dale a un clip otra paleta de color y otro ambiente, plano a plano.",
    labels: { video: "Video", palette: "Paleta" },
  },
  "ai-influencer": {
    title: "AI Influencer",
    description: "Crea tu propio personaje a partir de sus rasgos: tipo, cuerpo, pelo, estilo, edad y más.",
    labels: {
      type: "Tipo de personaje",
      gender: "Género",
      build: "Complexión",
      hair: "Peinado",
      hair_color: "Color de pelo",
      style: "Estilo",
      ethnicity: "Origen",
      age: "Edad",
      details: "Detalles extra",
      ratio: "Formato",
    },
    placeholders: { details: "pecas, piercing dorado en la nariz, bigote" },
  },
  "influencer-motion": {
    title: "Movimiento del influencer",
    description: "Convierte a tu personaje en un video listo para publicar con un movimiento viral.",
    labels: { character: "Imagen del personaje", motion: "Movimiento", resolution: "Calidad" },
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
  "warm golden hour sunlight from the side": "sol cálido de hora dorada de lado",
  "soft studio key light with a gentle rim light": "luz de estudio suave con contraluz",
  "neon pink and blue rim lights": "contraluces de neón rosa y azul",
  "dramatic low-key spotlight from above": "foco dramático desde arriba",
  "soft overcast daylight": "luz de día nublado",
  "warm candlelight": "luz de velas",
  "moonlight at night": "luz de luna",
  "teal and orange blockbuster grade": "verde azulado y naranja de taquilla",
  "warm vintage film with faded blacks": "película vintage cálida",
  "cool desaturated nordic tones": "tonos nórdicos fríos",
  "soft pastel tones": "pasteles suaves",
  "high contrast black and white": "blanco y negro contrastado",
  "neon cyberpunk magenta and cyan": "neón cyberpunk magenta y cian",
  human: "humano",
  "bold-looking human": "humano atrevido",
  "extreme stylized human": "humano extremo",
  "insect-headed humanoid": "insecto",
  "frog-headed humanoid": "rana",
  "cat-headed humanoid": "gato",
  "dog-headed humanoid": "perro",
  "rodent-headed humanoid": "roedor",
  "bird-headed humanoid": "ave",
  woman: "mujer",
  man: "hombre",
  "non-binary person": "no binario",
  slim: "delgada",
  athletic: "atlética",
  "fit hourglass": "curvilínea",
  average: "media",
  curvy: "con curvas",
  "plus-size": "talla grande",
  muscular: "musculosa",
  "ultra muscular": "ultra musculosa",
  "long straight hair": "largo y liso",
  "curly afro": "afro rizado",
  "blunt bob with bangs": "bob con flequillo",
  "buzz cut": "rapado",
  "slicked-back hair": "peinado hacia atrás",
  "messy wolf cut": "wolf cut",
  "long braids": "trenzas largas",
  "bald head": "calvo",
  black: "negro",
  brown: "castaño",
  "platinum blonde": "rubio platino",
  "copper red": "cobrizo",
  "silver grey": "gris plata",
  "pastel pink": "rosa pastel",
  "electric blue": "azul eléctrico",
  streetwear: "streetwear",
  "quiet luxury": "lujo discreto",
  "tailored suit": "traje a medida",
  "vintage 70s": "años 70",
  "avant-garde fashion": "moda vanguardista",
  "sporty athleisure": "deportivo",
  "elegant evening wear": "elegante",
  "athlete sportswear": "deportista",
  "casual shorts": "pantaloneta",
  "sleeveless tank top": "camisa esqueleto",
  "long maxi skirt": "falda larga",
  "mini skirt": "falda corta",
  "tight bodycon dress": "vestido ajustado",
  "loose flowy dress": "vestido suelto",
  "Latin American": "latino",
  "East Asian": "asiático oriental",
  "South Asian": "surasiático",
  Black: "afrodescendiente",
  "Middle Eastern": "de Oriente Medio",
  "white European": "europeo",
  "early 20s": "20 y pocos",
  "30s": "30 y tantos",
  "50s": "50 y tantos",
  "70s": "70 y tantos",
  "walks confidently toward the camera": "camina hacia la cámara",
  "does a runway catwalk turn": "giro de pasarela",
  "dances to an upbeat trending beat": "baila un ritmo de moda",
  "talks to the camera like a vlog": "habla a cámara como en un vlog",
  "slow-motion hair flip and smile": "mueve el pelo en cámara lenta",
  "jumps and lands in a power pose": "salta y cae en pose",
};

const CATEGORY_ES: Record<string, string> = {
  Product: "Producto",
  Social: "Redes",
  Cinematic: "Cine",
  Animate: "Animar",
  Motion: "Movimiento",
  Apps: "Apps",
  Influencer: "Influencer",
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
