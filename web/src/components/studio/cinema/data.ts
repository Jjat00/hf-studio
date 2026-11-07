import {
  Activity,
  Anchor,
  AppWindow,
  ArrowBigDown,
  ArrowBigUp,
  ArrowLeft,
  ArrowLeftToLine,
  ArrowRight,
  ArrowRightToLine,
  Bot,
  Camera,
  ChevronsDown,
  ChevronsLeft,
  ChevronsRight,
  ChevronsUp,
  Circle,
  Drama,
  Drone,
  Expand,
  Eye,
  Film,
  Flame,
  Focus,
  Footprints,
  Ghost,
  Hand,
  Helicopter,
  Infinity as InfinityIcon,
  Lamp,
  LampCeiling,
  Laugh,
  Moon,
  Mountain,
  MoveDown,
  MoveHorizontal,
  MoveUp,
  Plane,
  Projector,
  RectangleHorizontal,
  RotateCcw,
  RotateCw,
  Scan,
  ScanFace,
  Shrink,
  Shuffle,
  Sparkles,
  Sun,
  Sunset,
  Timer,
  Video,
  Waves,
  Wind,
  Zap,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from "lucide-react";
import { l, type L } from "@/lib/i18n";
import { PALETTES } from "./palettes";

export { PALETTES };

/** Campos creativos de Cinema Studio 4.0. Omitidos = «Auto» (la API no acepta el literal "auto"). */
export const CINEMA_KEYS = [
  "genre",
  "era",
  "pacing",
  "camera_model",
  "camera_lens",
  "camera_aperture",
  "camera_movement",
  "color_palette",
  "light",
] as const;
export type CinemaKey = (typeof CINEMA_KEYS)[number];

/** Claves de cine presentes en el esquema; con menos de tres no vale la pena la barra de dirección. */
export function cinemaKeysOf(schema: { properties?: Record<string, unknown> }): CinemaKey[] {
  const props = schema.properties ?? {};
  const keys = CINEMA_KEYS.filter((k) => k in props);
  return keys.length >= 3 ? keys : [];
}

export type Option = { value: string; label: L; desc: L; icon: LucideIcon; tone?: string; image?: string };

/** Imágenes de Cinema Studio en `public/cinema/<grupo>/<valor>.webp`: fotogramas (género, época, tempo, luz,
 * movimiento) y productos con fondo transparente (cámaras, lentes, aperturas). */
export type CinemaImageGroup = "genre" | "era" | "pacing" | "gear" | "movement" | "light";
export const cinemaImage = (group: CinemaImageGroup, value: string) => `/cinema/${group}/${value}.webp`;

/** Miniaturas por defecto de las cuatro tarjetas del compositor. */
export const CARD_IMAGES = {
  film: "/cinema/cards/film-setup.webp",
  camera: "/cinema/cards/camera.webp",
  palette: "/cinema/cards/color-palette.webp",
  light: "/cinema/cards/lighting.webp",
} as const;

const withImages = <T extends Option>(group: CinemaImageGroup, list: T[]): T[] => list.map((o) => ({ ...o, image: cinemaImage(group, o.value) }));

export const GENRES: Option[] = withImages("genre", [
  { value: "epic", label: l("Épico", "Epic"), desc: l("Gran escala, héroes y paisajes amplios", "Grand scale, heroes and vast landscapes"), icon: Mountain, tone: "from-amber-500/50 via-orange-900/40 to-sky-900/50" },
  { value: "drama", label: l("Drama", "Drama"), desc: l("Personajes, emoción y conflicto íntimo", "Characters, emotion and intimate conflict"), icon: Drama, tone: "from-rose-900/60 via-stone-900/40 to-stone-800/40" },
  { value: "noir", label: l("Noir", "Noir"), desc: l("Sombras duras, crimen y misterio", "Hard shadows, crime and mystery"), icon: Moon, tone: "from-zinc-200/30 via-zinc-800/60 to-black" },
  { value: "comedy", label: l("Comedia", "Comedy"), desc: l("Ritmo ligero, situaciones y humor", "Light rhythm, situations and humor"), icon: Laugh, tone: "from-yellow-400/40 via-pink-500/30 to-sky-500/30" },
  { value: "horror", label: l("Terror", "Horror"), desc: l("Tensión, miedo y lo que no se ve", "Tension, fear and what you can't see"), icon: Ghost, tone: "from-red-950/80 via-black to-emerald-950/50" },
  { value: "action", label: l("Acción", "Action"), desc: l("Persecuciones, golpes y adrenalina", "Chases, hits and adrenaline"), icon: Flame, tone: "from-orange-500/50 via-red-800/40 to-zinc-900/60" },
]);

export const ERAS: Option[] = withImages("era", [
  { value: "1960s", label: l("Años 60", "1960s"), desc: l("Color saturado y estética de estudio clásico", "Saturated color and classic studio look"), icon: Film },
  { value: "1980s", label: l("Años 80", "1980s"), desc: l("Neón, humo y grano de blockbuster", "Neon, haze and blockbuster grain"), icon: Sparkles },
  { value: "1990s", label: l("Años 90", "1990s"), desc: l("Cine independiente, tonos fríos y verdosos", "Indie cinema, cool greenish tones"), icon: Video },
  { value: "2000s", label: l("Años 2000", "2000s"), desc: l("Digital temprano, alto contraste y desaturado", "Early digital, high contrast, desaturated"), icon: Projector },
  { value: "2020s", label: l("Años 2020", "2020s"), desc: l("Digital limpio y moderno", "Clean modern digital"), icon: Camera },
]);

export const PACINGS: Option[] = withImages("pacing", [
  { value: "chaotic", label: l("Caótico", "Chaotic"), desc: l("Cortes rápidos e irregulares, energía nerviosa", "Fast, irregular cuts and nervous energy"), icon: Shuffle, tone: "from-fuchsia-600/40 via-red-700/30 to-yellow-500/30" },
  { value: "dynamic", label: l("Dinámico", "Dynamic"), desc: l("Montaje ágil con un ritmo constante", "Brisk editing with a steady beat"), icon: Activity, tone: "from-lime-500/40 via-emerald-800/30 to-sky-800/40" },
  { value: "calm", label: l("Calmado", "Calm"), desc: l("Planos largos y transiciones suaves", "Long takes and gentle transitions"), icon: Waves, tone: "from-sky-500/40 via-indigo-900/40 to-slate-900/50" },
  { value: "single-shot", label: l("Plano único", "Single shot"), desc: l("Un solo plano continuo, sin cortes", "One continuous shot, no cuts"), icon: InfinityIcon, tone: "from-violet-500/40 via-slate-800/40 to-zinc-900/60" },
]);

export const CAMERAS: Option[] = withImages("gear", [
  { value: "modern", label: l("Digital moderna", "Modern digital"), desc: l("Sensor nítido y limpio", "Sharp, clean sensor"), icon: Camera },
  { value: "35mm-film", label: l("Película 35 mm", "35mm film"), desc: l("Grano fino y color orgánico", "Fine grain and organic color"), icon: Film },
  { value: "8mm-film", label: l("Película 8 mm", "8mm film"), desc: l("Casero: grano fuerte y viñeta", "Home movie: heavy grain and vignette"), icon: Projector },
  { value: "dv-camcorder", label: l("Videocámara DV", "DV camcorder"), desc: l("Video doméstico de los 2000", "2000s home video"), icon: Video },
]);

export const LENSES: Option[] = withImages("gear", [
  { value: "clean-sharp", label: l("Limpio y nítido", "Clean sharp"), desc: l("Sin distorsión ni destellos", "No distortion or flares"), icon: Circle },
  { value: "anamorphic", label: l("Anamórfico", "Anamorphic"), desc: l("Destellos horizontales y bokeh ovalado", "Horizontal flares and oval bokeh"), icon: RectangleHorizontal },
  { value: "vintage-anamorphic", label: l("Anamórfico antiguo", "Vintage anamorphic"), desc: l("Anamórfico con aberraciones suaves", "Anamorphic with soft aberrations"), icon: Scan },
  { value: "warm-vintage", label: l("Antiguo cálido", "Warm vintage"), desc: l("Óptica antigua, cálida y de bajo contraste", "Old glass, warm and low contrast"), icon: Sunset },
  { value: "halation-vintage", label: l("Antiguo con halo", "Halation vintage"), desc: l("Halo brillante alrededor de las luces", "Glowing halo around highlights"), icon: Sun },
]);

export const APERTURES: Option[] = withImages("gear", [
  { value: "f14-wide-open", label: l("f/1.4", "f/1.4"), desc: l("Muy abierto: fondo muy desenfocado", "Wide open: very blurred background"), icon: Circle },
  { value: "f4-moderate", label: l("f/4", "f/4"), desc: l("Desenfoque moderado", "Moderate blur"), icon: Circle },
  { value: "f11-deep-focus", label: l("f/11", "f/11"), desc: l("Foco profundo: todo nítido", "Deep focus: everything sharp"), icon: Circle },
]);

/** Desenfoque (px) del primer plano y del fondo para dibujar la profundidad de campo de cada apertura. */
export const APERTURE_BLUR: Record<string, number> = { "f14-wide-open": 5, "f4-moderate": 2, "f11-deep-focus": 0 };

export type MovementGroup = "pan" | "dolly" | "crane" | "zoom" | "special";
export type Movement = Option & { group: MovementGroup };

const mv = (value: string, group: MovementGroup, icon: LucideIcon, label: L, desc: L): Movement => ({ value, group, icon, label, desc, image: cinemaImage("movement", value) });

export const MOVEMENTS: Movement[] = [
  mv("static-shot", "special", Anchor, l("Plano fijo", "Static shot"), l("La cámara no se mueve", "The camera stays still")),
  mv("pan-left", "pan", ArrowLeft, l("Paneo a la izquierda", "Pan left"), l("Gira sobre su eje hacia la izquierda", "Turns on its axis to the left")),
  mv("pan-right", "pan", ArrowRight, l("Paneo a la derecha", "Pan right"), l("Gira sobre su eje hacia la derecha", "Turns on its axis to the right")),
  mv("tilt-up", "pan", ChevronsUp, l("Tilt arriba", "Tilt up"), l("Inclina la mirada hacia arriba", "Tilts the view upward")),
  mv("tilt-down", "pan", ChevronsDown, l("Tilt abajo", "Tilt down"), l("Inclina la mirada hacia abajo", "Tilts the view downward")),
  mv("whip-pan", "pan", Wind, l("Barrido rápido", "Whip pan"), l("Paneo veloz con desenfoque de movimiento", "Fast pan with motion blur")),
  mv("dolly-in", "dolly", Expand, l("Dolly in", "Dolly in"), l("Avanza hacia el sujeto", "Moves toward the subject")),
  mv("dolly-out", "dolly", Shrink, l("Dolly out", "Dolly out"), l("Se aleja del sujeto", "Moves away from the subject")),
  mv("truck-left", "dolly", ArrowLeftToLine, l("Travelling a la izquierda", "Truck left"), l("Se desplaza de lado hacia la izquierda", "Slides sideways to the left")),
  mv("truck-right", "dolly", ArrowRightToLine, l("Travelling a la derecha", "Truck right"), l("Se desplaza de lado hacia la derecha", "Slides sideways to the right")),
  mv("slider-left", "dolly", ChevronsLeft, l("Slider a la izquierda", "Slider left"), l("Deslizamiento corto y suave a la izquierda", "Short smooth slide to the left")),
  mv("slider-right", "dolly", ChevronsRight, l("Slider a la derecha", "Slider right"), l("Deslizamiento corto y suave a la derecha", "Short smooth slide to the right")),
  mv("tracking", "dolly", Footprints, l("Seguimiento", "Tracking"), l("Sigue al sujeto mientras avanza", "Follows the subject as it moves")),
  mv("side-tracking", "dolly", MoveHorizontal, l("Seguimiento lateral", "Side tracking"), l("Acompaña al sujeto desde un lado", "Moves alongside the subject")),
  mv("arc-left", "dolly", RotateCcw, l("Arco a la izquierda", "Arc left"), l("Rodea al sujeto hacia la izquierda", "Circles the subject to the left")),
  mv("arc-right", "dolly", RotateCw, l("Arco a la derecha", "Arc right"), l("Rodea al sujeto hacia la derecha", "Circles the subject to the right")),
  mv("crane-up", "crane", MoveUp, l("Grúa arriba", "Crane up"), l("Sube en altura y revela la escena", "Rises and reveals the scene")),
  mv("crane-down", "crane", MoveDown, l("Grúa abajo", "Crane down"), l("Baja desde lo alto hacia el sujeto", "Descends toward the subject")),
  mv("pedestal-up", "crane", ArrowBigUp, l("Pedestal arriba", "Pedestal up"), l("Sube en vertical sin inclinar", "Rises vertically without tilting")),
  mv("pedestal-down", "crane", ArrowBigDown, l("Pedestal abajo", "Pedestal down"), l("Baja en vertical sin inclinar", "Lowers vertically without tilting")),
  mv("drone-orbit", "crane", Drone, l("Órbita de dron", "Drone orbit"), l("Dron que gira alrededor desde el aire", "Drone circling from the air")),
  mv("aerial-pullback", "crane", Plane, l("Alejamiento aéreo", "Aerial pullback"), l("Se eleva y se aleja para mostrar el lugar", "Rises and pulls back to show the place")),
  mv("helicopter-shot", "crane", Helicopter, l("Plano de helicóptero", "Helicopter shot"), l("Vuelo amplio sobre el paisaje", "Wide flight over the landscape")),
  mv("slow-zoom-in", "zoom", ZoomIn, l("Zoom lento adentro", "Slow zoom in"), l("Acerca la imagen poco a poco", "Gradually tightens the frame")),
  mv("slow-zoom-out", "zoom", ZoomOut, l("Zoom lento afuera", "Slow zoom out"), l("Abre la imagen poco a poco", "Gradually widens the frame")),
  mv("crush-zoom", "zoom", Zap, l("Zoom de impacto", "Crush zoom"), l("Zoom brusco y rápido al sujeto", "Sudden fast zoom onto the subject")),
  mv("dolly-zoom", "zoom", Scan, l("Dolly zoom", "Dolly zoom"), l("Efecto vértigo: el fondo se estira", "Vertigo effect: the background stretches")),
  mv("rack-focus", "zoom", Focus, l("Cambio de foco", "Rack focus"), l("El foco pasa de un plano a otro", "Focus shifts between planes")),
  mv("handheld", "special", Hand, l("Cámara en mano", "Handheld"), l("Movimiento orgánico con leve temblor", "Organic motion with slight shake")),
  mv("pov", "special", Eye, l("Punto de vista", "POV"), l("Lo que ve el personaje", "What the character sees")),
  mv("snorricam", "special", ScanFace, l("Snorricam", "Snorricam"), l("Cámara sujeta al actor, el fondo se mueve", "Camera rigged to the actor, the world moves")),
  mv("robot-arm", "special", Bot, l("Brazo robótico", "Robot arm"), l("Movimiento preciso y veloz de brazo robótico", "Fast, precise robotic arm move")),
  mv("bullet-time", "special", Timer, l("Bullet time", "Bullet time"), l("Tiempo congelado mientras la cámara gira", "Frozen time while the camera circles")),
];

export const LIGHT_DIRECTIONS = ["top", "front", "right", "left", "back", "bottom"] as const;
export type LightDirection = (typeof LIGHT_DIRECTIONS)[number];

export type LightSource = { color: string; brightness: number; diffuse: number; direction: LightDirection };
export type LightPreview = { lights: LightSource[]; backdrop?: string; dark?: boolean };

export const LIGHTS: (Option & { preview: LightPreview })[] = withImages("light", [
  {
    value: "silhouette",
    label: l("Silueta", "Silhouette"),
    desc: l("Sujeto oscuro contra un fondo luminoso", "Dark subject against a bright background"),
    icon: Sunset,
    preview: { lights: [{ color: "#ffd6a0", brightness: 90, diffuse: 20, direction: "back" }], backdrop: "#f3c58a", dark: true },
  },
  {
    value: "practicals",
    label: l("Luces prácticas", "Practicals"),
    desc: l("Lámparas visibles en escena como fuente de luz", "Visible lamps in the scene as the light source"),
    icon: Lamp,
    preview: { lights: [{ color: "#ffb35c", brightness: 70, diffuse: 50, direction: "left" }, { color: "#ffcf87", brightness: 45, diffuse: 60, direction: "right" }] },
  },
  {
    value: "window",
    label: l("Ventana", "Window"),
    desc: l("Luz natural lateral que entra por una ventana", "Natural side light coming through a window"),
    icon: AppWindow,
    preview: { lights: [{ color: "#dbe8ff", brightness: 85, diffuse: 55, direction: "left" }] },
  },
  {
    value: "overhead-fall",
    label: l("Cenital", "Overhead fall"),
    desc: l("Luz que cae desde arriba con sombras marcadas", "Light falling from above with deep shadows"),
    icon: LampCeiling,
    preview: { lights: [{ color: "#fff1d6", brightness: 85, diffuse: 30, direction: "top" }] },
  },
  {
    value: "contre-jour",
    label: l("Contraluz", "Contre-jour"),
    desc: l("Luz trasera que dibuja el contorno", "Backlight that outlines the subject"),
    icon: Sun,
    preview: { lights: [{ color: "#ffe2b0", brightness: 95, diffuse: 35, direction: "back" }, { color: "#8aa0c8", brightness: 25, diffuse: 80, direction: "front" }] },
  },
  {
    value: "soft-cross",
    label: l("Cruzada suave", "Soft cross"),
    desc: l("Dos luces suaves cruzadas desde los lados", "Two soft lights crossing from the sides"),
    icon: Sparkles,
    preview: { lights: [{ color: "#ffd2b0", brightness: 65, diffuse: 80, direction: "left" }, { color: "#b9d4ff", brightness: 60, diffuse: 80, direction: "right" }] },
  },
]);

export type CustomPalette = { id: string; name: string; colors: string[] };
export type CustomLighting = { id: string; name: string; lights: LightSource[] };

/** Lo que la API no tiene como valor: secuencia de movimientos y paleta o iluminación propias. */
export type CinemaExtra = { movements: string[]; palette: CustomPalette | null; lighting: CustomLighting | null };
export const EMPTY_CINEMA: CinemaExtra = { movements: [], palette: null, lighting: null };

export const MAX_PALETTE_COLORS = 12;
export const MAX_LIGHTS = 4;

export const findOption = (list: Option[], value: unknown) => list.find((o) => o.value === value);
export const findPalette = (value: unknown) => PALETTES.find((p) => p.value === value);

/** Movimientos en orden: el primero vive en `camera_movement`; si el valor del formulario no coincide (p. ej. al
 * reutilizar una generación), manda el formulario. */
export function movementsOf(values: Record<string, unknown>, extra: CinemaExtra): string[] {
  const first = values.camera_movement;
  if (typeof first !== "string" || !first) return [];
  return extra.movements[0] === first ? extra.movements : [first];
}

/** Paleta propia activa: solo si no hay una paleta del catálogo elegida. */
export const customPaletteOf = (values: Record<string, unknown>, extra: CinemaExtra) => (values.color_palette ? null : extra.palette);
export const customLightingOf = (values: Record<string, unknown>, extra: CinemaExtra) => (values.light ? null : extra.lighting);

const movementText = (value: string) =>
  value === "pov" ? "POV shot" : (MOVEMENTS.find((m) => m.value === value)?.label.en ?? value.replace(/-/g, " ")).toLowerCase();

const DIRECTION_TEXT: Record<LightDirection, string> = {
  top: "from above",
  front: "from the front",
  right: "from the right",
  left: "from the left",
  back: "from behind",
  bottom: "from below",
};
const LIGHT_ROLE = ["key light", "fill light", "rim light", "accent light"];

function tempOf(hex: string) {
  const n = parseInt(hex.replace("#", ""), 16);
  if (Number.isNaN(n)) return "";
  const r = (n >> 16) & 255;
  const b = n & 255;
  return r - b > 40 ? "warm " : b - r > 40 ? "cool " : "neutral ";
}

export function lightingText(lights: LightSource[]) {
  const parts = lights.map((s, i) => {
    const soft = s.diffuse >= 60 ? "soft" : s.diffuse <= 30 ? "hard" : "medium";
    return `${LIGHT_ROLE[i] ?? `light ${i + 1}`} ${DIRECTION_TEXT[s.direction]}, ${tempOf(s.color)}${s.color.toLowerCase()}, ${s.brightness}% brightness, ${soft} (diffuse ${s.diffuse}%)`;
  });
  return `Lighting: ${parts.join("; ")}.`;
}

export function paletteText(colors: string[]) {
  const list = colors.map((c, i) => (i === 0 ? `${c.toLowerCase()} (main)` : c.toLowerCase())).join(", ");
  return `Color palette: ${list}; grade the image to these colors.`;
}

/** Frases que se añaden al prompt al enviar (no se tocan en el prompt visible). */
export function cinemaPromptExtras(values: Record<string, unknown>, extra: CinemaExtra): string[] {
  const out: string[] = [];
  const moves = movementsOf(values, extra);
  if (moves.length > 1) out.push(`Camera: ${moves.map(movementText).join(", then ")}.`);
  const palette = customPaletteOf(values, extra);
  if (palette?.colors.length) out.push(paletteText(palette.colors));
  const lighting = customLightingOf(values, extra);
  if (lighting?.lights.length) out.push(lightingText(lighting.lights));
  return out;
}

/** Entrada final para cotizar y generar: el primer movimiento en `camera_movement` y el resto, más la paleta
 * y la iluminación propias, como texto al final del prompt. Función pura. */
export function applyCinema(values: Record<string, unknown>, extra: CinemaExtra): Record<string, unknown> {
  const extras = cinemaPromptExtras(values, extra);
  if (!extras.length) return values;
  const prompt = typeof values.prompt === "string" ? values.prompt.trimEnd() : "";
  return { ...values, prompt: prompt ? `${prompt}\n\n${extras.join(" ")}` : extras.join(" ") };
}

/* ---------- Paletas propias: color ---------- */

export const normalizeHex = (raw: string) => {
  const s = raw.trim().replace(/^#?/, "#").toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(s)) return s;
  if (/^#[0-9a-f]{3}$/.test(s)) return `#${s[1]}${s[1]}${s[2]}${s[2]}${s[3]}${s[3]}`;
  return null;
};

const toHex = (r: number, g: number, b: number) => `#${[r, g, b].map((x) => Math.round(x).toString(16).padStart(2, "0")).join("")}`;

export function hslToHex(h: number, s: number, l: number) {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    return 255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)));
  };
  return toHex(f(0), f(8), f(4));
}

/** Paleta aleatoria armónica: un tono base, su complementario y variaciones de luz. */
export function randomPalette(count = 8): string[] {
  const base = Math.random() * 360;
  const hues = [base, base + 30, base - 30, base + 180, base + 150];
  return Array.from({ length: count }, (_, i) => {
    const h = (hues[i % hues.length] + 360) % 360;
    const light = i === 0 ? 0.45 : 0.12 + ((i * 0.37) % 0.8);
    const sat = 0.25 + Math.random() * 0.6;
    return hslToHex(h, sat, light);
  });
}

/** Colores dominantes de una imagen: cubetas de 4 bits por canal y se eligen las más pobladas que se distingan. */
export function dominantColors(data: Uint8ClampedArray, max = MAX_PALETTE_COLORS): string[] {
  const buckets = new Map<number, { n: number; r: number; g: number; b: number }>();
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] < 128) continue;
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const key = ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
    const cur = buckets.get(key) ?? { n: 0, r: 0, g: 0, b: 0 };
    cur.n += 1;
    cur.r += r;
    cur.g += g;
    cur.b += b;
    buckets.set(key, cur);
  }
  const sorted = [...buckets.values()].sort((a, b) => b.n - a.n).map((c) => [c.r / c.n, c.g / c.n, c.b / c.n] as const);
  const picked: (readonly [number, number, number])[] = [];
  for (const minDist of [48, 28, 12]) {
    for (const c of sorted) {
      if (picked.length >= max) break;
      if (picked.every((p) => Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]) >= minDist)) picked.push(c);
    }
  }
  return picked.map(([r, g, b]) => toHex(r, g, b));
}

/* ---------- Guardado local ---------- */

export const PALETTES_KEY = "hfs.cinema.palettes";
export const LIGHTS_KEY = "hfs.cinema.lights";

export function loadStored<T>(key: string): T[] {
  try {
    const raw = window.localStorage.getItem(key);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

export function saveStored<T>(key: string, list: T[]) {
  try {
    window.localStorage.setItem(key, JSON.stringify(list));
  } catch {
    /* sin almacenamiento (modo privado): se usa solo en esta sesión */
  }
}

export const newId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()));
