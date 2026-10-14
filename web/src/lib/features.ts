import { l, type L } from "./i18n";

/** Accesos de la portada (Explore), en el orden de la de Higgsfield. */
export type Feature = {
  title: L;
  description: L;
  href: string;
  kind: "Video" | "Image" | "Agents";
  badge?: "TOP" | "NEW";
  icon: "bars" | "frames" | "layers" | "wand" | "clock" | "swap" | "move" | "sparkles" | "brush" | "terminal" | "user" | "workflow" | "clapper";
  art: string;
};

/** Fila superior: tres tarjetas grandes con pie en mayúsculas. */
export const BANNERS: Feature[] = [
  { title: l("Seedance 2.5", "Seedance 2.5"), description: l("Videos de hasta 30 segundos desde texto, imagen, video o audio", "Up to 30-second videos from text, image, video or audio"), href: "/video?model=bytedance/seedance-2.5/text-to-video", kind: "Video", badge: "TOP", icon: "bars", art: "/art/text-to-video.webp" },
  { title: l("Higgsfield Genjutsu", "Higgsfield Genjutsu"), description: l("Subes un video. Salen versiones sin fin", "One upload in. Endless new versions out"), href: "/video?tab=genjutsu", kind: "Video", badge: "NEW", icon: "swap", art: "/art/object-swap.webp" },
  { title: l("AI Influencer", "AI Influencer"), description: l("Elige el look, añade movimiento y publica", "Pick the look, add motion and post"), href: "/influencer", kind: "Image", badge: "NEW", icon: "user", art: "/art/use-cases/character-scenes.webp" },
];

/** Rejilla junto a la promo: accesos compactos. */
export const TILES: Feature[] = [
  { title: l("Seedance 2.5", "Seedance 2.5"), description: l("El modelo de video más avanzado", "The most advanced video model"), href: "/video?model=bytedance/seedance-2.5/text-to-video", kind: "Video", badge: "TOP", icon: "bars", art: "" },
  { title: l("AI Influencer", "AI Influencer"), description: l("Tu próxima máquina de hype", "Build your next hype machine"), href: "/influencer", kind: "Image", badge: "NEW", icon: "user", art: "" },
  { title: l("Genjutsu", "Genjutsu"), description: l("Un video, muchas versiones", "One video, many versions"), href: "/video?tab=genjutsu", kind: "Video", badge: "NEW", icon: "swap", art: "" },
  { title: l("MCP para agentes", "MCP for Agents"), description: l("Claude Code y Codex crean por ti", "Claude Code and Codex create for you"), href: "/mcp", kind: "Agents", icon: "terminal", art: "" },
  { title: l("Cinema Studio 4.0", "Cinema Studio 4.0"), description: l("Escenas cinematográficas sin esfuerzo", "Create cinematic scenes effortlessly"), href: "/video?model=higgsfield/cinema-studio/4.0", kind: "Video", icon: "clapper", art: "" },
  { title: l("Spaces", "Spaces"), description: l("Un lienzo para cada flujo", "One canvas, every workflow"), href: "/spaces", kind: "Agents", badge: "NEW", icon: "workflow", art: "" },
];

/** Apps de un clic (presets de serie de la categoría Apps). */
export const APPS: Feature[] = [
  { title: l("Reiluminar", "Relight"), description: l("Otra luz, mismo sujeto", "New light, same subject"), href: "/presets/relight", kind: "Image", icon: "sparkles", art: "/art/image-edit.webp" },
  { title: l("Cambio de cara", "Face Swap"), description: l("Una cara en otra foto", "A face in another photo"), href: "/presets/face-swap", kind: "Image", icon: "user", art: "/art/use-cases/portrait-alive.webp" },
  { title: l("Cambio de personaje", "Character Swap"), description: l("Tu personaje en otra escena", "Your character in another scene"), href: "/presets/character-swap", kind: "Image", icon: "swap", art: "/art/use-cases/character-scenes.webp" },
  { title: l("Cambiar paleta", "Color Palette"), description: l("Otro ambiente de color", "A new color mood"), href: "/presets/color-palette", kind: "Image", icon: "brush", art: "/art/use-cases/restyle.webp" },
  { title: l("Reencuadrar", "Reframe"), description: l("Cualquier formato", "Any aspect ratio"), href: "/presets/reframe-image", kind: "Image", icon: "frames", art: "/art/use-cases/reel-covers.webp" },
  { title: l("Reiluminar video", "Video Relight"), description: l("La luz de un clip", "Relight a clip"), href: "/presets/video-relight", kind: "Video", icon: "sparkles", art: "/art/video-edit.webp" },
  { title: l("Etalonar video", "Video Color Grade"), description: l("Otra paleta para tu clip", "A new palette for your clip"), href: "/presets/video-color-grade", kind: "Video", icon: "brush", art: "/art/use-cases/establishing.webp" },
  { title: l("Multiplicador de anuncios", "Ad Multiplier"), description: l("Tu producto en cualquier anuncio", "Your product in any ad"), href: "/presets/ad-multiplier", kind: "Video", icon: "layers", art: "/art/use-cases/ad-multiplier.webp" },
];
