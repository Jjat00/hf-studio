/** Accesos de la portada (Explore): cada uno abre el estudio en su pestaña y modo. */
export type Feature = {
  title: string;
  description: string;
  href: string;
  kind: "Video" | "Image" | "Agents";
  badge?: "TOP" | "NEW";
  icon: "bars" | "frames" | "layers" | "wand" | "clock" | "swap" | "move" | "sparkles" | "brush" | "terminal";
  art: string;
};

export const FEATURES: Feature[] = [
  { title: "Seedance 2.0", description: "The most advanced text to video model", href: "/video?tab=create&mode=text", kind: "Video", badge: "TOP", icon: "bars", art: "/art/text-to-video.webp" },
  { title: "Start & End Frame", description: "Animate a photo or bridge two frames", href: "/video?tab=create&mode=frames", kind: "Video", badge: "NEW", icon: "frames", art: "/art/frames.webp" },
  { title: "Video References", description: "Copy camera, style and characters", href: "/video?tab=create&mode=references", kind: "Video", icon: "layers", art: "/art/references.webp" },
  { title: "Motion Control", description: "Your character performs any motion", href: "/video?tab=motion", kind: "Video", icon: "move", art: "/art/motion.webp" },
  { title: "Video Edit", description: "Rewrite any clip with a prompt", href: "/video?tab=edit&mode=edit", kind: "Video", icon: "wand", art: "/art/video-edit.webp" },
  { title: "Video Extend", description: "Continue the shot where it ended", href: "/video?tab=edit&mode=extend", kind: "Video", icon: "clock", art: "/art/video-extend.webp" },
  { title: "Objects Swap", description: "One upload in. Endless new versions", href: "/video?tab=edit&mode=swap", kind: "Video", icon: "swap", art: "/art/object-swap.webp" },
  { title: "Soul 2.0", description: "Visuals that look shot, not generated", href: "/image?tab=create&mode=text", kind: "Image", badge: "TOP", icon: "sparkles", art: "/art/text-to-image.webp" },
  { title: "Image Edit", description: "Edit any part of a photo with text", href: "/image?tab=create&mode=edit", kind: "Image", icon: "brush", art: "/art/image-edit.webp" },
  { title: "MCP for Agents", description: "Claude Code and Codex create for you", href: "/mcp", kind: "Agents", badge: "NEW", icon: "terminal", art: "/art/mcp.webp" },
];
