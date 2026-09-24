import { l, type L } from "./i18n";
import type { ModelSummary } from "./types";

export type Mode = {
  key: string;
  label: L;
  icon: "type" | "image" | "layers" | "wand" | "clock" | "swap" | "move" | "sparkles" | "brush";
  defaultModel: string;
  filter: (m: ModelSummary) => boolean;
  hero: { title: L; subtitle: L; tone: "lime" | "pink" | "blue" | "amber" | "violet"; art: string };
  /** Etiquetas de las ranuras de medios propias de este modo: campo → [título, pista]. */
  labels?: Record<string, [L, L]>;
};

export type Tab = { key: string; label: L; modes: Mode[]; empty: EmptyState };

export type EmptyState = {
  title: L;
  steps: { title: L; body: L }[];
};

const has = (m: ModelSummary, cap: string) => m.capabilities.includes(cap);
const isVideo = (m: ModelSummary) => m.output === "video";
const genjutsu = l("Higgsfield Genjutsu", "Higgsfield Genjutsu");
const generate = l("Generar", "Generate");
const writePrompt = l("Escribe el prompt", "Write the prompt");

export const VIDEO_TABS: Tab[] = [
  {
    key: "create",
    label: l("Crear video", "Create Video"),
    empty: {
      title: l("Del concepto al corte final en segundos", "From concept to final cut in seconds"),
      steps: [
        {
          title: l("Sube lo que quieras", "Input anything"),
          body: l("Sube un fotograma inicial y otro final, clips de referencia, o empieza solo con un prompt.", "Upload a start and end frame, reference clips, or simply start with a text prompt."),
        },
        {
          title: writePrompt,
          body: l("Dirige la escena, la cámara y el ritmo con lenguaje natural.", "Use natural language to direct the scene, the camera and the pacing."),
        },
        {
          title: generate,
          body: l("Recibe video de alta fidelidad en minutos. Descárgalo, reutilízalo o itera sobre el resultado.", "Receive high-fidelity video in minutes. Download, reuse or iterate on the result."),
        },
      ],
    },
    modes: [
      {
        key: "text",
        label: l("Texto", "Text"),
        icon: "type",
        defaultModel: "bytedance/seedance-2.0/text-to-video",
        filter: (m) => isVideo(m) && m.id.includes("text-to-video"),
        hero: { title: l("Texto a video", "Text to video"), subtitle: l("Del prompt al plano cinematográfico", "From prompt to cinematic shot"), tone: "lime", art: "/art/text-to-video.webp" },
      },
      {
        key: "frames",
        label: l("Inicio y final", "Start & End"),
        icon: "image",
        defaultModel: "bytedance/seedance-2.0/image-to-video",
        filter: (m) => isVideo(m) && (m.id.includes("image-to-video") || m.id.includes("first-last-frame")),
        hero: { title: l("Fotograma inicial y final", "Start & end frame"), subtitle: l("Anima una imagen o une dos fotogramas", "Animate an image or bridge two frames"), tone: "blue", art: "/art/frames.webp" },
        labels: {
          image_url: [l("Fotograma inicial", "Start frame"), l("La imagen con la que empieza el video", "The image the video starts from")],
          end_image_url: [l("Fotograma final", "End frame"), l("Dónde debe terminar el plano", "Where the shot should land")],
        },
      },
      {
        key: "references",
        label: l("Referencias", "References"),
        icon: "layers",
        defaultModel: "bytedance/seedance-2.0/reference-to-video",
        filter: (m) =>
          isVideo(m) &&
          (has(m, "reference-to-video") || /(video|image)-reference/.test(m.id) || m.id.includes("cinema-studio")),
        hero: { title: l("Referencias de video", "Video references"), subtitle: l("Copia la cámara, el estilo y los personajes de tus clips", "Copy camera, style and characters from your clips"), tone: "violet", art: "/art/references.webp" },
        labels: {
          video_urls: [l("Añadir videos de referencia", "Add reference videos"), l("Cámara, movimiento o estilo a seguir · hasta 15 s cada uno", "Camera, motion or style to follow · up to 15s each")],
          image_urls: [l("Añadir elementos", "Add elements"), l("Personajes, productos o lugares", "Characters, products or locations")],
        },
      },
    ],
  },
  {
    key: "genjutsu",
    label: l("Genjutsu", "Genjutsu"),
    empty: {
      title: l("Convierte un video en muchos", "Turn one video into many"),
      steps: [
        { title: l("Añade un video de referencia", "Add a reference video"), body: l("De 4 a 30 segundos. Se conservan su movimiento, su ritmo y su cámara.", "4 to 30 seconds. Its motion, timing and camera are kept.") },
        { title: l("Añade tus elementos", "Add your elements"), body: l("Hasta ocho personajes, lugares o productos para cambiar el reparto de la escena.", "Up to eight characters, locations or products to recast the scene.") },
        { title: generate, body: l("Cambia el reparto del movimiento, o sustituye elementos concretos sin tocar el resto.", "Recast the motion, or swap specific elements while keeping the rest untouched.") },
      ],
    },
    modes: [
      {
        key: "motion",
        label: l("Transferir movimiento", "Motion transfer"),
        icon: "move",
        defaultModel: "higgsfiled/genjutsu/motion-transfer/v1.0",
        filter: (m) => m.id.includes("genjutsu/motion-transfer"),
        hero: { title: genjutsu, subtitle: l("Manipula la realidad · cambia quién hace el movimiento", "Reality manipulation · recast the motion"), tone: "lime", art: "/art/references.webp" },
        labels: {
          video_url: [l("Añade un video de referencia", "Add a reference video"), l("para extraer el movimiento · 4–30 segundos", "to extract motion · 4–30 seconds")],
          image_urls: [l("Añade tus elementos", "Add your elements"), l("Personajes, lugares o productos · hasta 8", "Characters, locations or products · up to 8")],
        },
      },
      {
        key: "swap",
        label: l("Cambiar objetos", "Objects swap"),
        icon: "swap",
        defaultModel: "higgsfiled/genjutsu/object-swap/v1.0",
        filter: (m) => m.id.includes("genjutsu/object-swap"),
        hero: { title: genjutsu, subtitle: l("Manipula la realidad · cambia un elemento y conserva el resto", "Reality manipulation · swap one element, keep the rest"), tone: "violet", art: "/art/object-swap.webp" },
        labels: {
          video_url: [l("Añade un video de referencia", "Add a reference video"), l("4–30 segundos · al menos 640×640 px por fotograma", "4–30 seconds · at least 640×640 px per frame")],
          image_urls: [l("Añade el objeto nuevo", "Add the new object"), l("Producto, prenda o accesorio a colocar · hasta 8", "Product, outfit or prop to swap in · up to 8")],
        },
      },
    ],
  },
  {
    key: "edit",
    label: l("Editar video", "Edit Video"),
    empty: {
      title: l("Convierte un video en muchos", "Turn one video into many"),
      steps: [
        { title: l("Sube un clip", "Upload a clip"), body: l("Parte de tu propio material o de una generación anterior.", "Start from your own footage or from a previous generation.") },
        { title: l("Describe el cambio", "Describe the change"), body: l("Cambia su estilo, sustituye objetos o alarga el plano sin volver a rodar.", "Restyle it, swap objects or extend the shot without reshooting.") },
        { title: l("Conserva el resto", "Keep the rest"), body: l("Todo lo que no pidas cambiar queda intacto.", "Everything you don't ask to change stays untouched.") },
      ],
    },
    modes: [
      {
        key: "edit",
        label: l("Editar", "Edit"),
        icon: "wand",
        defaultModel: "bytedance/seedance-2.5/video-edit",
        filter: (m) => has(m, "video-edit"),
        hero: { title: l("Editar video", "Video edit"), subtitle: l("Reescribe un clip con un prompt", "Rewrite a clip with a prompt"), tone: "pink", art: "/art/video-edit.webp" },
        labels: { video_url: [l("Añade un video para editar", "Add a video to edit"), l("Clip MP4 a transformar", "MP4 clip to transform")] },
      },
      {
        key: "extend",
        label: l("Extender", "Extend"),
        icon: "clock",
        defaultModel: "bytedance/seedance-2.5/video-extend",
        filter: (m) => has(m, "video-extend"),
        hero: { title: l("Extender video", "Video extend"), subtitle: l("Continúa el plano donde terminó", "Continue the shot where it ended"), tone: "amber", art: "/art/video-extend.webp" },
        labels: { video_url: [l("Añade un video para extender", "Add a video to extend"), l("El nuevo metraje sigue desde su último fotograma", "The new footage continues from its last frame")] },
      },
    ],
  },
  {
    key: "motion",
    label: l("Movimiento", "Motion Control"),
    empty: {
      title: l("Del concepto al corte final en segundos", "From concept to final cut in seconds"),
      steps: [
        { title: l("Sube lo que quieras", "Input anything"), body: l("Sube un video de referencia del movimiento y una imagen de tu personaje.", "Upload a motion reference video and an image of your character.") },
        { title: writePrompt, body: l("Si quieres, describe la escena, la ropa o el lugar.", "Optionally describe the scene, the outfit or the setting.") },
        { title: l("Genera con Kling", "Generate with Kling"), body: l("Tu personaje hace el movimiento, plano a plano.", "Your character performs the motion, shot by shot.") },
      ],
    },
    modes: [
      {
        key: "motion",
        label: l("Transferir movimiento", "Motion transfer"),
        icon: "move",
        defaultModel: "kling-video/v3/motion-control/std",
        filter: (m) => m.id.includes("motion-control"),
        hero: { title: l("Control de movimiento", "Motion control"), subtitle: l("Controla el movimiento con videos de referencia", "Control motion with video references"), tone: "lime", art: "/art/motion.webp" },
        labels: {
          video_url: [l("Añade el movimiento a copiar", "Add motion to copy"), l("Duración del video: 3–30 segundos", "Video duration: 3–30 seconds")],
          image_url: [l("Añade tu personaje", "Add your character"), l("Imagen con la cara y el cuerpo visibles", "Image with visible face and body")],
          image_urls: [l("Añade tu personaje", "Add your character"), l("Imagen con la cara y el cuerpo visibles", "Image with visible face and body")],
        },
      },
    ],
  },
];

export const IMAGE_TABS: Tab[] = [
  {
    key: "create",
    label: l("Crear imagen", "Create Image"),
    empty: {
      title: l("Imágenes que parecen fotografiadas, no generadas", "Visuals that look shot, not generated"),
      steps: [
        { title: l("Elige un modelo", "Pick a model"), body: l("Soul, Recraft, Ideogram, Qwen, Grok o Z-Image.", "Soul, Recraft, Ideogram, Qwen, Grok or Z-Image.") },
        { title: writePrompt, body: l("Encuadre, luz, lente y estilo en una sola frase.", "Framing, light, lens and style in a single sentence.") },
        { title: generate, body: l("Itera rápido y lleva tu mejor fotograma a video con un clic.", "Iterate fast, then bring your best frame to video in one click.") },
      ],
    },
    modes: [
      {
        key: "text",
        label: l("Texto a imagen", "Text to image"),
        icon: "sparkles",
        defaultModel: "higgsfield-ai/soul/v2/standard",
        filter: (m) => m.output === "image" && has(m, "text-to-image"),
        hero: { title: l("Texto a imagen", "Text to image"), subtitle: l("Fotografía editorial a partir de una frase", "Editorial photography from a sentence"), tone: "pink", art: "/art/text-to-image.webp" },
      },
      {
        key: "edit",
        label: l("Editar imagen", "Edit image"),
        icon: "brush",
        defaultModel: "alibaba/qwen-image-3/edit",
        filter: (m) => m.output === "image" && (has(m, "edit") || has(m, "image-edit") || has(m, "image-references")),
        hero: { title: l("Editar imagen", "Image edit"), subtitle: l("Cambia partes de una foto con un prompt", "Change parts of a photo with a prompt"), tone: "blue", art: "/art/image-edit.webp" },
        labels: { image_urls: [l("Añade imágenes para editar", "Add images to edit"), l("La foto y, si quieres, referencias", "The photo plus optional references")] },
      },
    ],
  },
];
