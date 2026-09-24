import type { JSONSchema } from "./types";

/** Tipos de control con los que se pinta cada campo del input_schema de un modelo. */
export type Field =
  | { kind: "prompt"; key: string; schema: JSONSchema; required: boolean }
  | { kind: "media"; key: string; schema: JSONSchema; required: boolean; media: "image" | "video" | "audio"; multiple: boolean; max: number; label: string; hint: string }
  | { kind: "enum"; key: string; schema: JSONSchema; required: boolean; options: (string | number)[] }
  | { kind: "range"; key: string; schema: JSONSchema; required: boolean; min: number; max: number; integer: boolean }
  | { kind: "number"; key: string; schema: JSONSchema; required: boolean; integer: boolean }
  | { kind: "toggle"; key: string; schema: JSONSchema; required: boolean }
  | { kind: "text"; key: string; schema: JSONSchema; required: boolean; multiline: boolean }
  | { kind: "json"; key: string; schema: JSONSchema; required: boolean };

const MEDIA_LABELS: Record<string, [string, string]> = {
  image_url: ["Start frame", "The image the video starts from"],
  first_frame_url: ["Start frame", "The image the video starts from"],
  end_image_url: ["End frame", "The image the video ends on"],
  last_frame_url: ["End frame", "The image the video ends on"],
  last_image_url: ["End frame", "The image the video ends on"],
  image_reference_url: ["Reference image", "Style or subject to follow"],
  image_urls: ["Reference images", "Characters, objects or style"],
  input_images: ["Input images", "Photos of the character or product"],
  video_url: ["Reference video", "Motion or clip to transform"],
  video_urls: ["Reference videos", "Camera, motion or style to follow"],
  audio_url: ["Audio", "Voice or music to sync"],
  audio_urls: ["Reference audio", "Voice or music to sync"],
};

/** Orden en que aparecen los ajustes, imitando a Higgsfield: calidad, duración, formato, audio. */
const ORDER = ["mode", "resolution", "quality", "duration", "aspect_ratio", "generate_audio", "sound", "seed"];

function typeOf(s: JSONSchema): string | undefined {
  return Array.isArray(s.type) ? s.type.find((t) => t !== "null") : s.type;
}

function mediaKind(key: string): "image" | "video" | "audio" | null {
  if (!/(_url|_urls)$/.test(key) && key !== "input_images") return null;
  if (key.startsWith("video")) return "video";
  if (key.startsWith("audio")) return "audio";
  if (/image|frame/.test(key)) return "image";
  return null;
}

export function requiredKeys(schema: JSONSchema): Set<string> {
  return new Set(schema.required ?? []);
}

export function fieldsFor(schema: JSONSchema): Field[] {
  const props = schema.properties ?? {};
  const req = requiredKeys(schema);
  const fields: Field[] = [];
  for (const [key, s] of Object.entries(props)) {
    const required = req.has(key);
    const type = typeOf(s);
    const media = mediaKind(key);
    if (key === "prompt" && type === "string") {
      fields.push({ kind: "prompt", key, schema: s, required });
    } else if (media) {
      const multiple = type === "array";
      const [label, hint] = MEDIA_LABELS[key] ?? [s.title ?? key, ""];
      fields.push({ kind: "media", key, schema: s, required, media, multiple, max: multiple ? (s.maxItems ?? 4) : 1, label, hint });
    } else if (s.enum) {
      fields.push({ kind: "enum", key, schema: s, required, options: s.enum });
    } else if ((type === "integer" || type === "number") && s.minimum !== undefined && s.maximum !== undefined) {
      fields.push({ kind: "range", key, schema: s, required, min: s.minimum, max: s.maximum, integer: type === "integer" });
    } else if (type === "integer" || type === "number") {
      fields.push({ kind: "number", key, schema: s, required, integer: type === "integer" });
    } else if (type === "boolean") {
      fields.push({ kind: "toggle", key, schema: s, required });
    } else if (type === "string") {
      fields.push({ kind: "text", key, schema: s, required, multiline: /prompt|description|text/.test(key) });
    } else {
      fields.push({ kind: "json", key, schema: s, required });
    }
  }
  const rank = (f: Field) => {
    const i = ORDER.indexOf(f.key);
    return i === -1 ? ORDER.length : i;
  };
  return fields.sort((a, b) => rank(a) - rank(b));
}

/** Valores iniciales: los `default` del esquema. */
export function defaultsFor(schema: JSONSchema): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [key, s] of Object.entries(schema.properties ?? {})) {
    if (s.default !== undefined) values[key] = s.default;
  }
  return values;
}

/** Quita vacíos antes de enviar: el backend valida contra el esquema completo. */
export function cleanInput(values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(values)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v) && v.length === 0) continue;
    out[k] = v;
  }
  return out;
}

export function humanize(key: string) {
  const map: Record<string, string> = {
    resolution: "Quality",
    quality: "Quality",
    duration: "Duration",
    aspect_ratio: "Aspect ratio",
    generate_audio: "Audio",
    sound: "Sound",
    seed: "Seed",
    mode: "Mode",
    negative_prompt: "Negative prompt",
    multi_shots: "Multi-shot",
    multi_prompt: "Shot prompts",
    num_images: "Images",
    batch_size: "Images",
    style: "Style",
    enhance_prompt: "Enhance prompt",
  };
  return map[key] ?? key.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
