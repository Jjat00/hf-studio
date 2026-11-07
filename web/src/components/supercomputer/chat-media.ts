import type { ChatMessage, ChatPart } from "@/lib/studio";
import { modelLabel, outputSrc } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/**
 * Medios del chat que el usuario cita con @imagenN, @videoN o @audioN: sus adjuntos (en orden), los resultados de las
 * generaciones lanzadas desde las propuestas (en el orden en que aparecen) y los adjuntos aún sin enviar. Cada tipo se
 * numera por separado. Una generación en curso ya ocupa su número, para que no cambie al terminar.
 */
export type MediaKind = "image" | "video" | "audio";
export type ChatMedia = {
  kind: MediaKind;
  n: number;
  url: string;
  /** URL para mostrarla (las salidas pueden servirse desde HF Studio). */
  src: string;
  content_type: string;
  /** «adjunto» o el modelo que la generó. */
  label: string;
  /** false: la generación aún no terminó (tiene número, pero no se puede citar todavía). */
  ready: boolean;
  /** Adjunto del compositor, sin enviar. */
  pending?: boolean;
  /** La generación falló o se canceló: guarda su número para no recorrer los demás, pero no se puede citar. */
  failed?: boolean;
};

const WORDS: Record<"es" | "en", Record<MediaKind, string>> = {
  es: { image: "imagen", video: "video", audio: "audio" },
  en: { image: "image", video: "video", audio: "audio" },
};

export function mediaName(m: Pick<ChatMedia, "kind" | "n">, locale: string) {
  return `${WORDS[locale === "en" ? "en" : "es"][m.kind]}${m.n}`;
}

/** @imagen2, @image2, @video1, @audio3 (cualquiera de los dos idiomas). */
export const MENTION = /@(imagen|image|video|audio)([1-9]\d{0,2})\b/gi;

export function kindOf(url: string, contentType?: string | null): MediaKind {
  const type = contentType?.split("/")[0];
  if (type === "video" || type === "audio" || type === "image") return type;
  if (/\.(mp4|mov|webm|m4v)(\?|$)/i.test(url)) return "video";
  if (/\.(mp3|wav|m4a|ogg|aac|flac)(\?|$)/i.test(url)) return "audio";
  return "image";
}

const DEFAULT_TYPE: Record<MediaKind, string> = { image: "image/png", video: "video/mp4", audio: "audio/mpeg" };

type Source = Omit<ChatMedia, "n">;

function partsMedia(parts: ChatPart[], launched: Record<string, string[]>, jobs: Record<string, Generation>, out: Source[]) {
  for (const p of parts) {
    if (p.type !== "proposal" || p.proposal.kind === "element") continue;
    const saved = p.proposal.job_ids?.length ? p.proposal.job_ids : p.proposal.job_id ? [p.proposal.job_id] : [];
    const ids = [...saved, ...(launched[p.proposal.tool_use_id] ?? []).filter((id) => !saved.includes(id))];
    const label = modelLabel(p.proposal.model_title).name;
    for (const id of ids) {
      const g = jobs[id];
      // Una que falló o se canceló conserva su número (no se puede citar): así las demás no se recorren y una mención
      // ya escrita nunca pasa a señalar otro medio.
      const failed = Boolean(g?.terminal && g.status !== "completed");
      const o = g?.status === "completed" ? g.outputs.find((x) => x.kind === "video" || x.kind === "image" || x.kind === "audio") : undefined;
      if (g?.status === "completed" && !o) continue;
      const kind: MediaKind = o ? kindOf(o.url, o.content_type || `${o.kind}/`) : p.proposal.output;
      const type = o?.content_type && o.content_type.startsWith(`${kind}/`) ? o.content_type : DEFAULT_TYPE[kind];
      out.push({ kind, url: o?.url ?? `job:${id}`, src: o ? outputSrc(o) : "", content_type: type, label, ready: Boolean(o), failed });
    }
  }
}

export function collectChatMedia(opts: {
  messages: ChatMessage[];
  pending: ChatMessage | null;
  draftParts: ChatPart[] | null;
  composer: { url: string; content_type: string }[];
  launched: Record<string, string[]>;
  jobs: Record<string, Generation>;
  attachedLabel: string;
  pendingLabel: string;
}): ChatMedia[] {
  const sources: Source[] = [];
  const user = (m: Extract<ChatMessage, { role: "user" }>) =>
    m.attachments.forEach((url, i) => {
      const kind = kindOf(url, m.attachment_kinds?.[i] ? `${m.attachment_kinds[i]}/` : null);
      sources.push({ kind, url, src: url, content_type: DEFAULT_TYPE[kind], label: opts.attachedLabel, ready: true });
    });
  for (const m of opts.messages) {
    if (m.role === "user") user(m);
    else partsMedia(m.parts, opts.launched, opts.jobs, sources);
  }
  if (opts.pending?.role === "user") user(opts.pending);
  if (opts.draftParts) partsMedia(opts.draftParts, opts.launched, opts.jobs, sources);
  for (const a of opts.composer) {
    const kind = kindOf(a.url, a.content_type);
    sources.push({ kind, url: a.url, src: a.url, content_type: a.content_type || DEFAULT_TYPE[kind], label: opts.pendingLabel, ready: true, pending: true });
  }
  const count: Record<MediaKind, number> = { image: 0, video: 0, audio: 0 };
  const seen = new Set<string>();
  const out: ChatMedia[] = [];
  for (const src of sources) {
    if (seen.has(src.url)) continue; // la misma URL otra vez conserva su primer número
    seen.add(src.url);
    out.push({ ...src, n: ++count[src.kind] });
  }
  return out;
}

/** Los medios citados en el texto, con el nombre tal como se escribió (sin @). Ignora los que no existen o no terminaron. */
export function citedRefs(text: string, media: ChatMedia[]) {
  const refs: { name: string; url: string; content_type: string }[] = [];
  for (const m of text.matchAll(MENTION)) {
    const word = m[1].toLowerCase();
    const kind: MediaKind = word === "imagen" ? "image" : (word as MediaKind);
    const item = media.find((x) => x.kind === kind && x.n === Number(m[2]) && x.ready);
    const name = `${word}${m[2]}`;
    if (item && !refs.some((r) => r.name === name)) refs.push({ name, url: item.url, content_type: item.content_type });
  }
  return refs.slice(0, 10);
}
