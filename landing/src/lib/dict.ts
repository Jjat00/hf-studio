export type Locale = "es" | "en";

export const REPO = "https://github.com/Jjat00/hf-studio";
export const AUTHOR = "https://jaimeaza.tech";

/** Textos de la landing. Misma forma en los dos idiomas: el tipo sale del español. */
const es = {
  nav: { examples: "Ejemplos", audio: "Audio", agents: "Agentes", start: "Empezar", star: "Estrella en GitHub" },
  hero: {
    eyebrow: "Open source · MIT · Windows, macOS y Linux",
    title1: "Tu propio estudio de IA.",
    title2: "Todos los grandes modelos.",
    body: "Video, imagen, voz, música y efectos con los modelos de Higgsfield y ElevenLabs, desde una interfaz web o desde tus agentes por MCP. Lo instalas en tu máquina y pagas solo lo que generas.",
    ctaRepo: "Ver en GitHub",
    ctaPromo: "Ver el promo",
    prompt: "Un auto deportivo en una carretera costera al atardecer, toma de dron",
    model: "Seedance 2.0",
    generate: "Generar",
  },
  stats: [
    { value: "82", label: "modelos de video e imagen" },
    { value: "25", label: "herramientas MCP" },
    { value: "5", label: "funciones de audio" },
    { value: "0", label: "suscripciones" },
  ],
  promo: {
    title: "48 segundos hechos con HF Studio",
    body: "La música, la voz del locutor y las escenas de este video salieron del propio estudio.",
  },
  examples: {
    kicker: "Ejemplos reales",
    title: "Hecho con HF Studio",
    body: "Generaciones de verdad, sin retoques: el modelo y la técnica de cada una van en la tarjeta.",
  },
  caps: {
    title: "Cada forma de crear video e imagen",
    body: "Los 82 endpoints de Higgsfield con su esquema completo, buscables por lo que hacen y no por la marca. El formulario sale del esquema de cada modelo.",
    items: [
      { art: "text-to-video", title: "Texto a video", desc: "Seedance, Kling, Wan, Hailuo, LTX, Grok Imagine…" },
      { art: "frames", title: "Inicio y final", desc: "Das el primer y el último fotograma; el modelo anima el resto." },
      { art: "references", title: "Referencias", desc: "Personajes, productos y lugares que se mantienen en cada toma." },
      { art: "video-edit", title: "Editar video", desc: "Cambia el estilo o la escena conservando cortes y movimiento." },
      { art: "video-extend", title: "Extender", desc: "Alarga un clip con continuidad de cámara y de acción." },
      { art: "motion", title: "Motion control", desc: "Copia el movimiento de un video a tu personaje." },
      { art: "object-swap", title: "Genjutsu", desc: "Sustituye una persona u objeto y deja el fondo intacto." },
      { art: "text-to-image", title: "Texto a imagen", desc: "Soul, Recraft, Ideogram, Qwen, Grok y más." },
      { art: "image-edit", title: "Editar imagen", desc: "Retoca o recompone una imagen con una frase." },
    ],
  },
  audio: {
    kicker: "Audio con ElevenLabs",
    title: "Voces, música y efectos",
    body: "Opcional: con una clave de ElevenLabs se activan el cambio de voz, el texto a voz, los efectos, la música y el aislamiento de voz. Todo queda en la sonoteca para reutilizarlo sin volver a pagar.",
    voiceChange: {
      title: "Cambiar la voz de un video",
      body: "Elige un tramo, una voz y, si quieres, un efecto (grave, monstruo o fantasma). Se conserva lo que dice y su ritmo.",
      before: "Original",
      after: "Voz cambiada",
      hint: "Activa el sonido y compara.",
    },
    tts: {
      title: "Texto a voz",
      body: "Locutor colombiano con eleven_v4, la voz del promo.",
      quote: "«¿Creas contenido con IA y tienes todo repartido en mil pestañas? Por eso creé HF Studio: tu propio estudio de IA, gratis y open source…»",
    },
    free: {
      title: "Voces gratis en español",
      body: "45 voces de edge-tts, con Colombia primero, para probar un texto sin gastar.",
      voices: ["Gonzalo · Colombia", "Salomé · Colombia"],
    },
    music: {
      title: "Música",
      body: "Pista instrumental a 118 BPM, generada para el promo.",
    },
    sfx: {
      title: "Efectos de sonido",
      body: "Describe el sonido y listo. Toca uno:",
      items: ["Trueno", "Murciélagos", "Caja registradora", "Obturador", "Campana", "Risa de bruja"],
    },
  },
  agents: {
    kicker: "Servidor MCP",
    title1: "Tus agentes",
    title2: "generan por ti",
    body: "HF Studio también es un servidor MCP. Conéctalo a Claude Code, Codex, Claude Desktop o ChatGPT y tu agente busca el modelo, te dice cuánto cuesta, espera tu OK y genera.",
    rule: "La regla: un agente no puede gastar créditos sin cotizar antes esa misma petición. Cada herramienta de pago exige un quote_id de un solo uso.",
    connect: "Conecta tu agente con un comando",
    chat: {
      user: "Hazme un video de 5 s de tinta de colores en agua, en cámara lenta",
      tools: ["recommend_models", "get_model", "estimate_cost"],
      quote: "Wan 2.7 · texto a video, 5 s a 720p. Cuesta 8 créditos (0,50 USD). ¿Lo genero?",
      ok: "Dale",
      done: "Listo: tinta.mp4 descargado en ./outputs",
    },
  },
  more: {
    title: "Y todo lo demás",
    items: [
      { icon: "library", title: "Biblioteca", desc: "Todo lo que generas desde la UI y desde los agentes, con su origen y su configuración completa." },
      { icon: "coins", title: "Costo antes de generar", desc: "Al lado del botón en la UI y obligatorio en el MCP." },
      { icon: "layers", title: "Presets y lotes", desc: "Recetas con variables y variantes con un costo total." },
      { icon: "sparkles", title: "Recomendador", desc: "Dices lo que quieres, en español o inglés, y te sugiere modelos con su precio." },
      { icon: "book", title: "12 casos de uso", desc: "Tutoriales paso a paso para la UI y para tus agentes." },
      { icon: "shield", title: "Trabajos persistentes", desc: "Cola local, idempotencia y copia local de cada resultado (Higgsfield solo los guarda 7 días)." },
    ],
    shots: ["Estudio de video", "Catálogo de modelos", "Casos de uso"],
  },
  start: {
    kicker: "Empieza en un minuto",
    title: "Instálalo en tu máquina",
    body: "Clona el repo y ejecuta el script: te pide la clave de Higgsfield (y, si quieres, la de ElevenLabs), la valida sin gastar créditos y abre el estudio en localhost:3000.",
    reqs: ["Python 3.12 y uv", "Node.js 20 y pnpm", "ffmpeg para el audio", "Clave de la API de Higgsfield"],
    note: "Sin suscripción: usa la API de Higgsfield, así que pagas solo lo que generas.",
    copy: "Copiar",
    copied: "Copiado",
  },
  footer: {
    title: "Si te sirve, déjale una estrella",
    body: "HF Studio es gratis y open source. Una estrella en GitHub ayuda a que más gente lo encuentre.",
    cta: "Dar una estrella",
    disclaimer: "Proyecto personal, sin relación con Higgsfield ni ElevenLabs. Usa sus APIs públicas con tus propias claves.",
    by: "Hecho por",
  },
};

export type Dict = typeof es;

const en: Dict = {
  nav: { examples: "Examples", audio: "Audio", agents: "Agents", start: "Get started", star: "Star on GitHub" },
  hero: {
    eyebrow: "Open source · MIT · Windows, macOS and Linux",
    title1: "Your own AI studio.",
    title2: "Every major model.",
    body: "Video, image, voice, music and sound effects with the Higgsfield and ElevenLabs models, from a web UI or from your agents over MCP. It runs on your machine and you only pay for what you generate.",
    ctaRepo: "View on GitHub",
    ctaPromo: "Watch the promo",
    prompt: "A sports car on a coastal road at sunset, drone shot",
    model: "Seedance 2.0",
    generate: "Generate",
  },
  stats: [
    { value: "82", label: "video and image models" },
    { value: "25", label: "MCP tools" },
    { value: "5", label: "audio features" },
    { value: "0", label: "subscriptions" },
  ],
  promo: {
    title: "48 seconds made with HF Studio",
    body: "The music, the voiceover and the shots in this video all came out of the studio itself (voiceover in Spanish).",
  },
  examples: {
    kicker: "Real examples",
    title: "Made with HF Studio",
    body: "Real generations, untouched: each card shows the model and technique behind it.",
  },
  caps: {
    title: "Every way to make video and images",
    body: "All 82 Higgsfield endpoints with their full schema, searchable by what they do instead of by brand. Each model's form is built from its schema.",
    items: [
      { art: "text-to-video", title: "Text to video", desc: "Seedance, Kling, Wan, Hailuo, LTX, Grok Imagine…" },
      { art: "frames", title: "First & last frame", desc: "Give the first and last frame; the model animates the rest." },
      { art: "references", title: "References", desc: "Characters, products and places that stay consistent across shots." },
      { art: "video-edit", title: "Video edit", desc: "Change the style or the scene while keeping cuts and motion." },
      { art: "video-extend", title: "Extend", desc: "Make a clip longer with continuous camera and action." },
      { art: "motion", title: "Motion control", desc: "Copy the motion from a video onto your character." },
      { art: "object-swap", title: "Genjutsu", desc: "Swap a person or an object and keep the background intact." },
      { art: "text-to-image", title: "Text to image", desc: "Soul, Recraft, Ideogram, Qwen, Grok and more." },
      { art: "image-edit", title: "Image edit", desc: "Retouch or recompose an image with one sentence." },
    ],
  },
  audio: {
    kicker: "Audio with ElevenLabs",
    title: "Voices, music and sound effects",
    body: "Optional: an ElevenLabs key unlocks voice change, text to speech, sound effects, music and voice isolation. Everything lands in the sound library so you can reuse it instead of paying again.",
    voiceChange: {
      title: "Change the voice in a video",
      body: "Pick a segment, a voice and, if you like, an effect (deep, monster or ghost). What is said and its timing stay the same.",
      before: "Original",
      after: "New voice",
      hint: "Turn the sound on and compare.",
    },
    tts: {
      title: "Text to speech",
      body: "A Colombian narrator with eleven_v4, the voice from the promo (in Spanish).",
      quote: "“Do you make content with AI and have everything scattered across a thousand tabs? That's why I built HF Studio: your own AI studio, free and open source…”",
    },
    free: {
      title: "Free Spanish voices",
      body: "45 edge-tts voices, Colombia first, to try a script without spending.",
      voices: ["Gonzalo · Colombia", "Salomé · Colombia"],
    },
    music: {
      title: "Music",
      body: "An instrumental track at 118 BPM, made for the promo.",
    },
    sfx: {
      title: "Sound effects",
      body: "Describe the sound and you're done. Tap one:",
      items: ["Thunder", "Bats", "Cash register", "Camera shutter", "Bell", "Witch laugh"],
    },
  },
  agents: {
    kicker: "MCP server",
    title1: "Your agents",
    title2: "generate for you",
    body: "HF Studio is also an MCP server. Connect it to Claude Code, Codex, Claude Desktop or ChatGPT and your agent finds the model, tells you the price, waits for your OK and generates.",
    rule: "The rule: an agent cannot spend credits without first quoting that exact request. Every paid tool requires a single-use quote_id.",
    connect: "Connect your agent with one command",
    chat: {
      user: "Make me a 5 s slow-motion video of colorful ink in water",
      tools: ["recommend_models", "get_model", "estimate_cost"],
      quote: "Wan 2.7 · text to video, 5 s at 720p. It costs 8 credits ($0.50). Shall I generate it?",
      ok: "Go ahead",
      done: "Done: tinta.mp4 saved to ./outputs",
    },
  },
  more: {
    title: "And everything else",
    items: [
      { icon: "library", title: "Library", desc: "Everything you generate from the UI and from agents, with its origin and full configuration." },
      { icon: "coins", title: "Cost before generating", desc: "Next to the button in the UI, and required over MCP." },
      { icon: "layers", title: "Presets and batches", desc: "Recipes with variables, and variants with a total price." },
      { icon: "sparkles", title: "Recommender", desc: "Say what you want, in English or Spanish, and get models with their price." },
      { icon: "book", title: "12 use cases", desc: "Step-by-step tutorials for the UI and for your agents." },
      { icon: "shield", title: "Persistent jobs", desc: "Local queue, idempotency and a local copy of every output (Higgsfield only keeps them 7 days)." },
    ],
    shots: ["Video studio", "Model catalog", "Use cases"],
  },
  start: {
    kicker: "Up and running in a minute",
    title: "Install it on your machine",
    body: "Clone the repo and run the script: it asks for your Higgsfield key (and, optionally, ElevenLabs), validates it without spending credits and opens the studio at localhost:3000.",
    reqs: ["Python 3.12 and uv", "Node.js 20 and pnpm", "ffmpeg for audio", "A Higgsfield API key"],
    note: "No subscription: it uses the Higgsfield API, so you only pay for what you generate.",
    copy: "Copy",
    copied: "Copied",
  },
  footer: {
    title: "If it helps, leave a star",
    body: "HF Studio is free and open source. A star on GitHub helps more people find it.",
    cta: "Star the repo",
    disclaimer: "Personal project, not affiliated with Higgsfield or ElevenLabs. It uses their public APIs with your own keys.",
    by: "Made by",
  },
};

export const DICTS: Record<Locale, Dict> = { es, en };
