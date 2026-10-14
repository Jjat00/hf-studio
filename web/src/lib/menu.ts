import {
  AudioLines,
  Boxes,
  Brush,
  Clapperboard,
  Clock,
  Crop,
  Film,
  ImagePlus,
  Layers,
  type LucideIcon,
  Megaphone,
  Mic,
  Move,
  Music,
  Palette,
  Repeat,
  ScanFace,
  Sparkles,
  SunMedium,
  UserRound,
  Users,
  Video,
  Volume2,
  Wand2,
  Waves,
  Workflow,
} from "lucide-react";
import { l, type L } from "./i18n";

/**
 * Menús desplegables de la barra, al estilo de Higgsfield: cada sección (Imagen, Video, Audio) abre dos
 * columnas, «Funciones» (lo que puedes hacer) y «Modelos» (con qué). Todo apunta a rutas del estudio.
 */
export type MenuEntry = { title: L; description: L; href: string; icon: LucideIcon; badge?: "TOP" | "NEW" };
export type MegaMenu = { key: "image" | "video" | "audio"; href: string; features: MenuEntry[]; models: MenuEntry[] };

const img = (id: string) => `/image?model=${id}`;
const vid = (id: string) => `/video?model=${id}`;

export const MEGA_MENUS: MegaMenu[] = [
  {
    key: "image",
    href: "/image",
    features: [
      { title: l("Crear imagen", "Create Image"), description: l("Genera imágenes con IA", "Generate AI images"), href: "/image", icon: ImagePlus },
      { title: l("Editar imagen", "Edit Image"), description: l("Cambia partes de una foto con texto", "Change parts of a photo with text"), href: "/image?tab=create&mode=edit", icon: Brush },
      { title: l("Spaces", "Spaces"), description: l("Lienzo de nodos con flujos repetibles", "Node canvas with repeatable workflows"), href: "/spaces", icon: Workflow, badge: "NEW" },
      { title: l("AI Influencer", "AI Influencer"), description: l("Crea y anima tu propio personaje", "Create and animate your own character"), href: "/influencer", icon: UserRound, badge: "NEW" },
      { title: l("Reiluminar", "Relight"), description: l("Cambia la posición, el color y la intensidad de la luz", "Adjust lighting position, color and brightness"), href: "/presets/relight", icon: SunMedium },
      { title: l("Cambiar paleta", "Change Color Palette"), description: l("Otra paleta, otros tonos, otro ambiente", "Adjust palette, tones and overall mood"), href: "/presets/color-palette", icon: Palette },
      { title: l("Cambio de cara", "Face Swap"), description: l("Cambios de cara realistas", "Create realistic face swaps"), href: "/presets/face-swap", icon: ScanFace },
      { title: l("Cambio de personaje", "Character Swap"), description: l("Pon a tu personaje en otra escena", "Create realistic character swaps"), href: "/presets/character-swap", icon: Repeat },
      { title: l("Reencuadrar", "Reframe"), description: l("Lleva una foto a cualquier formato", "Take a photo to any aspect ratio"), href: "/presets/reframe-image", icon: Crop },
    ],
    models: [
      { title: l("Higgsfield Soul 2.0", "Higgsfield Soul 2.0"), description: l("Moda ultrarrealista de nueva generación", "Next generation ultra-realistic fashion visuals"), href: img("higgsfield-ai/soul/v2/standard"), icon: Sparkles, badge: "TOP" },
      { title: l("Higgsfield Soul Cinema", "Higgsfield Soul Cinema"), description: l("Estética cinematográfica de película", "Cinematic film-grade aesthetic"), href: img("higgsfield-ai/soul/cinema"), icon: Film },
      { title: l("Marketing Studio Sunburst", "Marketing Studio Sunburst"), description: l("Calidad excepcional y ediciones precisas", "Exceptional quality, precise edits"), href: img("marketing-studio/image/sunburst"), icon: Sparkles, badge: "NEW" },
      { title: l("Marketing Studio Flare", "Marketing Studio Flare"), description: l("Imágenes cotidianas impactantes, rápido", "Stunning everyday images, fast"), href: img("marketing-studio/image/flare"), icon: Sparkles },
      { title: l("Grok Imagine 2.0", "Grok Imagine 2.0"), description: l("Genera y edita en alta resolución, de xAI", "High-resolution generation and editing by xAI"), href: img("xai/grok-imagine-image-2.0"), icon: Wand2 },
      { title: l("Qwen Image 3", "Qwen Image 3"), description: l("Edición fiel con hasta 3 referencias", "Faithful editing with up to 3 references"), href: img("alibaba/qwen-image-3/edit"), icon: Brush },
      { title: l("Ideogram 4.0", "Ideogram 4.0"), description: l("El mejor texto dentro de la imagen", "Best-in-class text inside images"), href: img("ideogram/v4.0"), icon: ImagePlus },
      { title: l("Recraft V4.1", "Recraft V4.1"), description: l("Imágenes fotorrealistas y expresivas", "Photorealistic and expressive images"), href: img("recraft/v4.1/text-to-image"), icon: Palette },
      { title: l("Z-Image", "Z-Image"), description: l("Retratos realistas al instante", "Instant lifelike portraits"), href: img("z-image/turbo"), icon: UserRound },
    ],
  },
  {
    key: "video",
    href: "/video",
    features: [
      { title: l("Crear video", "Create Video"), description: l("Genera videos con IA", "Generate AI videos"), href: "/video", icon: Video },
      { title: l("Cinema Studio", "Cinema Studio"), description: l("Video cinematográfico con referencias", "Cinematic video from your references"), href: vid("higgsfield/cinema-studio/4.0"), icon: Clapperboard },
      { title: l("Spaces", "Spaces"), description: l("Lienzo de nodos con flujos repetibles", "Node canvas with repeatable workflows"), href: "/spaces", icon: Workflow, badge: "NEW" },
      { title: l("Editar video", "Edit Video"), description: l("Edita escenas, planos y elementos", "Edit scenes, shots and elements"), href: "/video?tab=edit&mode=edit", icon: Wand2 },
      { title: l("Extender video", "Extend Video"), description: l("Continúa el plano donde terminó", "Continue the shot where it ended"), href: "/video?tab=edit&mode=extend", icon: Clock },
      { title: l("Control de movimiento", "Motion Control"), description: l("Tu personaje hace cualquier movimiento", "Your character performs any motion"), href: "/video?tab=motion", icon: Move },
      { title: l("Elementos", "Elements"), description: l("Personajes y productos reutilizables", "Reusable characters and products"), href: "/elements", icon: Boxes },
      { title: l("Reiluminar video", "Video Relight"), description: l("Cambia la luz de un clip", "Change the lighting of a clip"), href: "/presets/video-relight", icon: SunMedium },
      { title: l("Etalonar video", "Change Color Palette"), description: l("Otra paleta y otro ambiente para tu clip", "A new palette and mood for your clip"), href: "/presets/video-color-grade", icon: Palette },
      { title: l("Multiplicador de anuncios", "Ad Multiplier"), description: l("Cambia el producto de un anuncio", "Swap the product in an ad"), href: "/presets/ad-multiplier", icon: Megaphone },
      { title: l("Casos de uso", "Use cases"), description: l("Recetas listas por objetivo", "Ready-made recipes by goal"), href: "/use-cases", icon: Layers },
    ],
    models: [
      { title: l("Seedance 2.5", "Seedance 2.5"), description: l("Videos cinematográficos de hasta 30 segundos", "Cinematic videos up to 30 seconds"), href: vid("bytedance/seedance-2.5/text-to-video"), icon: AudioLines, badge: "TOP" },
      { title: l("Higgsfield Genjutsu", "Higgsfield Genjutsu"), description: l("Transfiere movimiento o cambia objetos de un video", "Transfer motion or swap objects from a reference video"), href: "/video?tab=genjutsu", icon: Sparkles, badge: "NEW" },
      { title: l("Kling 3.0", "Kling 3.0"), description: l("Videos cinematográficos con audio", "Cinematic videos with audio"), href: vid("kling-video/v3.0/pro/text-to-video"), icon: Film },
      { title: l("Kling Motion Control", "Kling Motion Control"), description: l("Transfiere el movimiento de un video a una imagen", "Transfer motion from video to image"), href: "/video?tab=motion", icon: Move },
      { title: l("Kling O3 Edit", "Kling O3 Edit"), description: l("Edita videos con texto", "Edit videos with text prompts"), href: vid("kling-video/o3/video-edit"), icon: Wand2 },
      { title: l("MiniMax H3", "MiniMax H3"), description: l("Videos 2K desde texto, fotogramas o referencias", "2K videos from text, keyframes or references"), href: vid("minimax/h3/text-to-video"), icon: Waves },
      { title: l("Wan 3.0", "Wan 3.0"), description: l("Desde texto, fotogramas o referencias multimodales", "From text, keyframes or multimodal references"), href: vid("alibaba/wan-3.0/text-to-video"), icon: Waves },
      { title: l("Grok Imagine 1.5", "Grok Imagine 1.5"), description: l("Video cinematográfico con audio sincronizado", "Cinematic video with synchronized audio"), href: vid("xai/grok-imagine-video/v1.5/reference-to-video"), icon: Wand2 },
      { title: l("HappyHorse 1.1", "HappyHorse 1.1"), description: l("El modelo de video y audio n.º 1 de Alibaba", "Alibaba's #1 ranked video and audio model"), href: vid("alibaba/happy-horse/v1.1/text-to-video"), icon: Sparkles },
      { title: l("Seedance 2.0", "Seedance 2.0"), description: l("Texto, imagen y referencias a video", "Text, image and references to video"), href: vid("bytedance/seedance-2.0/text-to-video"), icon: AudioLines },
      { title: l("MiniMax Hailuo 2.3", "MiniMax Hailuo 2.3"), description: l("Video muy dinámico y rápido", "Fastest high-dynamic video"), href: vid("minimax/hailuo-2.3/standard/text-to-video"), icon: Waves },
      { title: l("LTX-2.5", "LTX-2.5"), description: l("Rápido y barato para iterar", "Fast and cheap to iterate"), href: vid("lightricks/ltx-2.5/text-to-video/fast"), icon: Film },
      { title: l("PixVerse V6", "PixVerse V6"), description: l("Efectos y estilos para redes", "Effects and styles for social"), href: vid("pixverse/v6/text-to-video"), icon: Film },
    ],
  },
  {
    key: "audio",
    href: "/audio",
    features: [
      { title: l("Texto a voz", "Text to Speech"), description: l("Genera voz a partir de texto", "Generate speech from text"), href: "/audio?tab=text-to-speech", icon: Mic },
      { title: l("Cambio de voz", "Voice Change"), description: l("Cambia la voz de cualquier video", "Swap voices in any video"), href: "/voice", icon: AudioLines },
      { title: l("Efectos de sonido", "Sound Effects"), description: l("Cualquier sonido descrito con palabras", "Any sound described in words"), href: "/audio?tab=sound-effects", icon: Volume2 },
      { title: l("Música", "Music"), description: l("Pistas originales a partir de un prompt", "Original tracks from a prompt"), href: "/audio?tab=music", icon: Music },
      { title: l("Aislar voz", "Voice Isolator"), description: l("Limpia la voz de ruido y música", "Clean speech from noise and music"), href: "/audio?tab=voice-isolator", icon: Waves },
      { title: l("Voces gratis", "Free voices"), description: l("Voces en español sin costo", "Spanish voices at no cost"), href: "/voices", icon: Users },
      { title: l("Sonoteca", "Sound library"), description: l("Tus sonidos ordenados y reutilizables", "Your sounds, sorted and reusable"), href: "/sounds", icon: Layers },
    ],
    models: [
      { title: l("Eleven v4", "Eleven v4"), description: l("Narración expresiva con control de estabilidad", "Expressive narration with stability controls"), href: "/audio?tab=text-to-speech", icon: AudioLines, badge: "NEW" },
      { title: l("Eleven v4 Turbo", "Eleven v4 Turbo"), description: l("Voz expresiva y rápida", "Fast expressive speech"), href: "/audio?tab=text-to-speech", icon: AudioLines, badge: "NEW" },
      { title: l("Eleven v3", "Eleven v3"), description: l("Emoción y entonación con etiquetas", "Emotion and delivery control via inline tags"), href: "/audio?tab=text-to-speech", icon: AudioLines },
      { title: l("Eleven Music", "Eleven Music"), description: l("Música con o sin letra", "Music with or without lyrics"), href: "/audio?tab=music", icon: Music },
      { title: l("Eleven Sound Effects", "Eleven Sound Effects"), description: l("Efectos y ambientes en bucle", "Effects and loopable ambiences"), href: "/audio?tab=sound-effects", icon: Volume2 },
    ],
  },
];
