import type { RunEstimate, Space, SpaceRun, SpaceSummary } from "./spaces";
import type { ApiErrorBody, FreeVoice, Generation, ModelDetail, ModelSummary, Preset, ProviderInfo, Sound, StudioElement, Voice, VoiceChangeBody, VoiceStatus } from "./types";

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
    public details?: { path: string; message: string }[] | Record<string, unknown>,
  ) {
    super(message);
  }
}

/** Errores por campo (422 invalid_input); otros errores traen detalles que no son una lista. */
export function fieldErrors(e: unknown): { path: string; message: string }[] | null {
  return e instanceof StudioError && Array.isArray(e.details) ? e.details : null;
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
  /** `maxUsd`: el precio que vio el usuario; si la opción más barata subió, la API responde 409 cost_changed. */
  generate: (
    model: string,
    input: Record<string, unknown>,
    idempotencyKey: string,
    keepSourceAudio = false,
    maxUsd?: number | null,
    hints: Record<string, number> = {},
    maxReserveUsd?: number | null,
    acceptUnknownCost = false,
  ) =>
    call<Generation>("/v1/generations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        model,
        input,
        keep_source_audio: keepSourceAudio,
        hints,
        ...(maxUsd != null ? { max_usd: maxUsd } : {}),
        ...(maxReserveUsd != null ? { max_reserve_usd: maxReserveUsd } : {}),
        ...(acceptUnknownCost ? { accept_unknown_cost: true } : {}),
      }),
    }),
  /** Aprueba el proveedor de respaldo más caro de una generación en awaiting_approval. */
  /** `acceptUnknown`: el usuario aceptó explícitamente un precio desconocido (sin `maxUsd`, sin tope). */
  approve: (id: string, maxUsd: number | null, maxReserveUsd?: number | null, acceptUnknown = false) =>
    call<Generation>(`/v1/generations/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...(maxUsd != null ? { max_usd: maxUsd } : {}),
        ...(maxReserveUsd != null ? { max_reserve_usd: maxReserveUsd } : {}),
        ...(acceptUnknown ? { accept_unknown_cost: true } : {}),
      }),
    }),
  providers: () => call<{ providers: ProviderInfo[] }>("/v1/providers"),
  voiceStatus: () => call<VoiceStatus>("/v1/voice/status"),
  freeVoices: () => call<{ voices: FreeVoice[] }>("/v1/voice/free-voices?lang=es"),
  /** URL del MP3 de una voz gratis diciendo el texto (gratis, se guarda en caché en el servidor). */
  freeSampleUrl: (voice: string, text: string, rate = "+0%") =>
    `${BASE}/v1/voice/free-sample?${new URLSearchParams({ voice, text, rate })}`,
  libraryVoices: (filters: { language?: string; accent?: string; gender?: string; search?: string }) =>
    call<{ voices: Voice[] }>(
      `/v1/voice/voices?${new URLSearchParams({ library: "true", limit: "60", ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v)) })}`,
    ),
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
  sounds: () => call<{ sounds: Sound[]; counts: Record<string, number>; categories: string[] }>("/v1/sounds?limit=500"),
  updateSound: (id: string, patch: { title?: string; category?: string; tags?: string[] }) =>
    call<Sound>(`/v1/sounds/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),
  importElevenlabs: () => call<{ imported: number; skipped: number }>("/v1/sounds/import-elevenlabs", { method: "POST" }),
  list: (limit = 60) => call<{ generations: Generation[] }>(`/v1/generations?limit=${limit}`),
  get: (id: string, wait = 0) => call<Generation>(`/v1/generations/${id}${wait ? `?wait=${wait}` : ""}`),
  presets: () => call<{ presets: Preset[] }>("/v1/presets"),
  preset: (slug: string) => call<Preset>(`/v1/presets/${slug}`),
  previewPreset: (slug: string, variables: Record<string, unknown>, hints: Record<string, number> = {}) =>
    call<{ model: string; input: Record<string, unknown>; missing_variables: string[]; estimate: Estimate }>(
      `/v1/presets/${slug}/run`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ variables, dry_run: true, hints }) },
    ),
  /** `maxUsd`: el precio que se mostró (dry_run); si subió, la API responde 409 cost_changed. */
  runPreset: (
    slug: string,
    variables: Record<string, unknown>,
    idempotencyKey: string,
    maxUsd?: number | null,
    maxReserveUsd?: number | null,
    acceptUnknownCost = false,
  ) =>
    call<Generation>(`/v1/presets/${slug}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        variables,
        ...(maxUsd != null ? { max_usd: maxUsd } : {}),
        ...(maxReserveUsd != null ? { max_reserve_usd: maxReserveUsd } : {}),
        ...(acceptUnknownCost ? { accept_unknown_cost: true } : {}),
      }),
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
  elements: () => call<{ elements: StudioElement[] }>("/v1/elements"),
  /** URL vigente de una salida propia para usarla como entrada de otra generación (gratis). */
  useOutput: (id: string, index = 0) =>
    call<{ url: string; kind: string; content_type: string }>(`/v1/generations/${id}/outputs/${index}/use`, {
      method: "POST",
    }),
  /** 2 a 4 imágenes JPG o PNG; `name` en minúsculas (letras, dígitos y _), se cita como @name. */
  /** `urls`: imágenes propias ya subidas (p. ej. una creación vía `useOutput`). */
  createElement: (name: string, description: string, files: File[], urls: string[] = []) => {
    const form = new FormData();
    form.append("name", name);
    form.append("description", description);
    for (const f of files) form.append("files", f);
    for (const u of urls) form.append("image_urls", u);
    return call<StudioElement>("/v1/elements", { method: "POST", body: form });
  },
  deleteElement: (id: string) => call<void>(`/v1/elements/${id}`, { method: "DELETE" }),
  spaces: () => call<{ spaces: SpaceSummary[] }>("/v1/spaces"),
  space: (id: string) => call<Space>(`/v1/spaces/${id}`),
  createSpace: (title?: string) =>
    call<Space>("/v1/spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(title ? { title } : {}),
    }),
  /** Guarda con la versión leída; si otra pestaña guardó antes, 409 version_conflict. */
  saveSpace: (id: string, body: { version: number; title?: string; graph?: unknown; cover?: string | null }) =>
    call<Space>(`/v1/spaces/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteSpace: (id: string) => call<void>(`/v1/spaces/${id}`, { method: "DELETE" }),
  /** Corrida en el servidor: `dry_run` cotiza cada paso; sin él arranca con el tope aprobado. */
  estimateRun: (id: string, body: { mode: "downstream" | "workflow"; node_id?: string; version: number }) =>
    call<RunEstimate>(`/v1/spaces/${id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, dry_run: true }),
    }),
  /** `idempotencyKey`: la misma por diálogo; reintentar tras perder la respuesta devuelve la misma corrida. */
  startRun: (
    id: string,
    body: { mode: "downstream" | "workflow"; node_id?: string; version: number; max_total_usd: number },
    idempotencyKey: string,
  ) =>
    call<SpaceRun>(`/v1/spaces/${id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  runs: (id: string, limit = 10) => call<{ runs: SpaceRun[] }>(`/v1/spaces/${id}/runs?limit=${limit}`),
  run: (id: string, runId: string) => call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}`),
  approveRun: (id: string, runId: string, body: { max_total_usd?: number; accept_unknown?: boolean }) =>
    call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelRun: (id: string, runId: string) => call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}/cancel`, { method: "POST" }),
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
  /** Proveedor elegido (el más barato) y el resto de opciones. */
  provider?: string | null;
  /** Retención inicial del elegido, mayor que su costo final (se devuelve la diferencia). */
  reserve_usd?: number | null;
  options?: EstimateOption[];
  excluded?: { provider: string; title: string; model?: string; reason: string; usd?: number | null; key_url?: string; billing_url?: string }[];
  savings_vs_higgsfield?: { usd: number; pct: number } | null;
};

export type EstimateOption = Omit<Estimate, "options" | "excluded" | "savings_vs_higgsfield" | "provider"> & {
  provider: string;
  title: string;
  model: string;
  official: boolean;
  notes: string[];
  /** Débito inicial mayor que el costo final (el proveedor devuelve la diferencia). */
  reserve_usd?: number | null;
};

/** Un costo positivo nunca se muestra como cero: por debajo de una milésima sale «<$0.001». */
export function formatUsd(usd: number) {
  if (usd === 0) return "$0.00";
  if (usd > 0 && usd < 0.001) return "<$0.001";
  return usd < 0.01 ? `$${usd.toFixed(3)}` : `$${usd.toFixed(2)}`;
}

/** «~$0.12» para un aproximado; sin la tilde cuando ya es una cota («<$0.001»). */
export function approxUsd(usd: number) {
  const text = formatUsd(usd);
  return text.startsWith("<") ? text : `~${text}`;
}

/** Texto corto del costo para botones, siempre en USD: «$1.51» o «~$1.51» (nunca créditos de Higgsfield). */
export function costShort(e: Estimate | null): string | null {
  if (!e) return null;
  if (e.kind === "exact" && e.usd !== null) return formatUsd(e.usd);
  if (e.kind === "approx" && e.usd !== null) return approxUsd(e.usd);
  return null;
}

/** URL reproducible de una salida: la copia local si existe (no caduca), si no la de Higgsfield. */
/** URL del navegador para una ruta de la API (p. ej. las imágenes de un elemento). */
export function apiSrc(path: string) {
  return BASE + path;
}

export function outputSrc(out: { url: string; file_url?: string }) {
  return out.file_url ? BASE + out.file_url : out.url;
}

/** «Seedance 2.0 — Text to video API» → { name: "Seedance 2.0", workflow: "Text to video" } */
export function modelLabel(title: string) {
  const [name, rest] = title.replace(/ API$/, "").split(" — ");
  return { name, workflow: rest ?? "" };
}
