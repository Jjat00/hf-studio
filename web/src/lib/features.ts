import { l, type L } from "./i18n";

/** Accesos de la portada (Explore): cada uno abre el estudio en su pestaña y modo. */
export type Feature = {
  title: L;
  description: L;
  href: string;
  kind: "Video" | "Image" | "Agents";
  badge?: "TOP" | "NEW";
  icon: "bars" | "frames" | "layers" | "wand" | "clock" | "swap" | "move" | "sparkles" | "brush" | "terminal";
  art: string;
};

export const FEATURES: Feature[] = [
  { title: l("Seedance 2.0", "Seedance 2.0"), description: l("El modelo de texto a video más avanzado", "The most advanced text to video model"), href: "/video?tab=create&mode=text", kind: "Video", badge: "TOP", icon: "bars", art: "/art/text-to-video.webp" },
  { title: l("Fotograma inicial y final", "Start & End Frame"), description: l("Anima una foto o une dos fotogramas", "Animate a photo or bridge two frames"), href: "/video?tab=create&mode=frames", kind: "Video", badge: "NEW", icon: "frames", art: "/art/frames.webp" },
  { title: l("Referencias de video", "Video References"), description: l("Copia la cámara, el estilo y los personajes", "Copy camera, style and characters"), href: "/video?tab=create&mode=references", kind: "Video", icon: "layers", art: "/art/references.webp" },
  { title: l("Control de movimiento", "Motion Control"), description: l("Tu personaje hace cualquier movimiento", "Your character performs any motion"), href: "/video?tab=motion", kind: "Video", icon: "move", art: "/art/motion.webp" },
  { title: l("Editar video", "Video Edit"), description: l("Reescribe cualquier clip con un prompt", "Rewrite any clip with a prompt"), href: "/video?tab=edit&mode=edit", kind: "Video", icon: "wand", art: "/art/video-edit.webp" },
  { title: l("Extender video", "Video Extend"), description: l("Continúa el plano donde terminó", "Continue the shot where it ended"), href: "/video?tab=edit&mode=extend", kind: "Video", icon: "clock", art: "/art/video-extend.webp" },
  { title: l("Higgsfield Genjutsu", "Higgsfield Genjutsu"), description: l("Subes un video. Salen versiones sin fin", "One upload in. Endless new versions"), href: "/video?tab=genjutsu", kind: "Video", badge: "NEW", icon: "swap", art: "/art/object-swap.webp" },
  { title: l("Soul 2.0", "Soul 2.0"), description: l("Imágenes que parecen fotografiadas, no generadas", "Visuals that look shot, not generated"), href: "/image?tab=create&mode=text", kind: "Image", badge: "TOP", icon: "sparkles", art: "/art/text-to-image.webp" },
  { title: l("Editar imagen", "Image Edit"), description: l("Edita cualquier parte de una foto con texto", "Edit any part of a photo with text"), href: "/image?tab=create&mode=edit", kind: "Image", icon: "brush", art: "/art/image-edit.webp" },
  { title: l("MCP para agentes", "MCP for Agents"), description: l("Claude Code y Codex crean por ti", "Claude Code and Codex create for you"), href: "/mcp", kind: "Agents", badge: "NEW", icon: "terminal", art: "/art/mcp.webp" },
];
