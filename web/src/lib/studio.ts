import type { ApiErrorBody, Generation, ModelDetail, ModelSummary, Preset, Voice, VoiceChangeBody, VoiceStatus } from "./types";

/** Cambio de voz con ElevenLabs: trabajo local de HF Studio, no un modelo del catálogo de Higgsfield. */
export const VOICE_MODEL = "elevenlabs/voice-changer";

/** Servicios de audio de ElevenLabs: servicio de la API → modelo del trabajo local. */
export const AUDIO_SERVICES = {
  "text-to-speech": "elevenlabs/text-to-speech",
  "sound-effects": "elevenlabs/sound-effects",
  music: "elevenlabs/music",
  "voice-isolator": "elevenlabs/voice-isolator",
} as const;
export type AudioService = keyof typeof AUDIO_SERVICES;
const AUDIO_MODEL_SET = new Set<string>(Object.values(AUDIO_SERVICES));

export function isAudioModel(model: string) {
  return AUDIO_MODEL_SET.has(model);
}

/** Tipo de salida de una generación: del catálogo de Higgsfield, video (cambio de voz) o audio (ElevenLabs). */
export function outputOf(model: string, models: Map<string, ModelSummary>): string | undefined {
  if (model === VOICE_MODEL) return "video";
  if (isAudioModel(model)) return "audio";
  return models.get(model)?.output;
}

/** Ruta para reutilizar los ajustes de una generación. */
export function reuseHref(model: string, id: string, models: Map<string, ModelSummary>) {
  if (model === VOICE_MODEL) return `/voice?reuse=${id}`;
  if (isAudioModel(model)) return `/audio?reuse=${id}`;
  return `/${models.get(model)?.output === "image" ? "image" : "video"}?reuse=${id}`;
}

/** Cliente del navegador: todo pasa por el proxy /api/studio, que añade la clave en el servidor. */
const BASE = "/api/studio";

export class StudioError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: { path: string; message: string }[],
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ApiErrorBody;
    throw new StudioError(
      body.error?.message ?? `Error ${res.status}`,
      res.status,
      body.error?.code,
      body.error?.details,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const studio = {
  models: (params: Record<string, string> = {}) =>
    call<{ synced_at: string; capabilities: string[]; models: ModelSummary[] }>(
      `/v1/models?${new URLSearchParams(params)}`,
    ),
  model: (id: string) => call<ModelDetail>(`/v1/models/${id}`),
  estimate: (model: string, input: Record<string, unknown>, hints: Record<string, number> = {}) =>
    call<Estimate>("/v1/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input, hints }),
    }),
  generate: (model: string, input: Record<string, unknown>, idempotencyKey: string, keepSourceAudio = false) =>
    call<Generation>("/v1/generations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ model, input, keep_source_audio: keepSourceAudio }),
    }),
  voiceStatus: () => call<VoiceStatus>("/v1/voice/status"),
  voices: (search: string, library: boolean) =>
    call<{ voices: Voice[] }>(
      `/v1/voice/voices?library=${library}&limit=40${search ? `&search=${encodeURIComponent(search)}` : ""}`,
    ),
  voiceEstimate: (body: VoiceChangeBody) =>
    call<Estimate & { seconds: number; start: number; end: number; voice_quote: string }>("/v1/voice/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  changeVoice: (body: VoiceChangeBody, idempotencyKey: string) =>
    call<Generation>("/v1/voice/changes", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  audioEstimate: (service: AudioService, body: Record<string, unknown>) =>
    call<Estimate & { units: number; audio_quote: string }>(`/v1/audio/${service}/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  createAudio: (service: AudioService, body: Record<string, unknown>, idempotencyKey: string) =>
    call<Generation>(`/v1/audio/${service}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  list: (limit = 60) => call<{ generations: Generation[] }>(`/v1/generations?limit=${limit}`),
  get: (id: string, wait = 0) => call<Generation>(`/v1/generations/${id}${wait ? `?wait=${wait}` : ""}`),
  presets: () => call<{ presets: Preset[] }>("/v1/presets"),
  preset: (slug: string) => call<Preset>(`/v1/presets/${slug}`),
  previewPreset: (slug: string, variables: Record<string, unknown>, hints: Record<string, number> = {}) =>
    call<{ model: string; input: Record<string, unknown>; missing_variables: string[]; estimate: Estimate }>(
      `/v1/presets/${slug}/run`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ variables, dry_run: true, hints }) },
    ),
  runPreset: (slug: string, variables: Record<string, unknown>, idempotencyKey: string) =>
    call<Generation>(`/v1/presets/${slug}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ variables }),
    }),
  savePreset: (generationId: string, slug: string, title: string) =>
    call<Preset>(`/v1/presets/from-generation/${generationId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, title }),
    }),
  deletePreset: (slug: string) => call<void>(`/v1/presets/${slug}`, { method: "DELETE" }),
  remove: (id: string) => call<void>(`/v1/generations/${id}`, { method: "DELETE" }),
  cancel: (id: string) => call<Generation>(`/v1/generations/${id}/cancel`, { method: "POST" }),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ id: string; url: string; content_type: string }>("/v1/uploads", {
      method: "POST",
      body: form,
    });
  },
};

/** Costo normalizado por la API: exacto, aproximado por fórmula, solo fórmula o no disponible. */
export type Estimate = {
  kind: "exact" | "approx" | "formula" | "unavailable";
  credits: number | null;
  usd: number | null;
  discount_pct: number | null;
  basis: string;
  missing: string[];
  description: string | null;
};

/** Un costo positivo nunca se muestra como cero: por debajo de una milésima sale «<$0.001». */
export function formatUsd(usd: number) {
  if (usd > 0 && usd < 0.001) return "<$0.001";
  return usd < 0.01 ? `$${usd.toFixed(3)}` : `$${usd.toFixed(2)}`;
}

/** «~$0.12» para un aproximado; sin la tilde cuando ya es una cota («<$0.001»). */
export function approxUsd(usd: number) {
  const text = formatUsd(usd);
  return text.startsWith("<") ? text : `~${text}`;
}

/** Texto corto del costo para botones: «✦ 8.57» (créditos) o «~$1.51». */
export function costShort(e: Estimate | null): string | null {
  if (!e) return null;
  if (e.kind === "exact" && e.credits !== null) return `${+e.credits.toFixed(3)}`;
  if (e.kind === "approx" && e.usd !== null) return approxUsd(e.usd);
  return null;
}

/** URL reproducible de una salida: la copia local si existe (no caduca), si no la de Higgsfield. */
export function outputSrc(out: { url: string; file_url?: string }) {
  return out.file_url ? BASE + out.file_url : out.url;
}

/** «Seedance 2.0 — Text to video API» → { name: "Seedance 2.0", workflow: "Text to video" } */
export function modelLabel(title: string) {
  const [name, rest] = title.replace(/ API$/, "").split(" — ");
  return { name, workflow: rest ?? "" };
}
