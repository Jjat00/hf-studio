import type { Flow, FlowSummary, RunEstimate, Space, SpaceRun, SpaceSummary } from "./spaces";
import type { LiveCategory } from "./influencer-data";
import { activeProject } from "./project";
import type { ApiErrorBody, ElementCategory, Project, ProjectFolder, ProjectSummary, FreeVoice, Generation, ModelDetail, ModelSummary, Preset, ProviderInfo, Sound, StudioElement, ModelStyle, Usage, Voice, VoiceChangeBody, VoiceDesignBody, VoicePreview, VoiceStatus } from "./types";

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

/** Ids que Higgsfield renombró (2026-10, errata «higgsfiled»): el historial, los presets y los Spaces viejos los
 *  guardan así. La API los resuelve al nuevo; aquí los mapas de modelos los aceptan también. */
const LEGACY_MODELS: Record<string, string> = {
  "higgsfiled/genjutsu/motion-transfer/v1.0": "higgsfield/genjutsu/motion-transfer/v1.0",
  "higgsfiled/genjutsu/object-swap/v1.0": "higgsfield/genjutsu/object-swap/v1.0",
};

/** Modelos por id, incluidos los ids viejos de `LEGACY_MODELS`. */
/** Generación en espera de aprobación; un paso de una corrida de Spaces se aprueba desde su corrida. */
export type PendingApproval = Generation & { space_run: { run_id: string; space_id: string; title: string } | null };

export function modelMap(list: ModelSummary[]): Map<string, ModelSummary> {
  const map = new Map(list.map((m) => [m.id, m]));
  for (const [old, current] of Object.entries(LEGACY_MODELS)) {
    const m = map.get(current);
    if (m) map.set(old, m);
  }
  return map;
}

/** Los modelos de un `modelMap` sin repetir los que también están bajo un id viejo (para listarlos). */
export function uniqueModels(map: Map<string, ModelSummary>): ModelSummary[] {
  return [...new Map([...map.values()].map((m) => [m.id, m])).values()];
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
    allowDuplicate = false,
    // Proyecto donde se guarda: sin indicarlo, el proyecto activo (null: ninguno).
    projectId: string | null = activeProject(),
    // Carpeta del proyecto (opcional).
    folderId: string | null = null,
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
        ...(allowDuplicate ? { allow_duplicate: true } : {}),
        ...(projectId ? { project_id: projectId } : {}),
        ...(projectId && folderId ? { folder_id: folderId } : {}),
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
  /** Gasto por día, proveedor y modelo; `days` 0 = todo. `utcOffset` en minutos (Bogotá = -300). */
  usage: (days: number, utcOffset: number) => call<Usage>(`/v1/usage?days=${days}&utc_offset=${utcOffset}`),
  /** Content Factory: estilos, plantillas y qué hace falta para escribir guiones y renderizar. */
  factory: (lang = "es") => call<FactoryInfo>(`/v1/factory?lang=${encodeURIComponent(lang)}`),
  /** Claude escribe el guion de cada episodio (solo cuesta tokens de Claude, `cost_usd`). */
  /** Lo máximo que puede costar escribir ese guion (no llama a Claude). */
  factoryScriptEstimate: (body: { topic: string; style: string; duration_seconds: number; episodes: number; language: string }) =>
    call<{ max_usd: number; model: string; available: boolean }>("/v1/factory/scripts/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  /** Escribe el guion con el tope que vio el usuario (`max_usd`); la misma clave no vuelve a cobrar un reintento. */
  factoryScripts: (
    body: { topic: string; style: string; duration_seconds: number; episodes: number; language: string; max_usd: number },
    idempotencyKey: string,
  ) =>
    call<FactoryScripts>("/v1/factory/scripts", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  voiceStatus: () => call<VoiceStatus>("/v1/voice/status"),
  freeVoices: (lang = "es") => call<{ voices: FreeVoice[] }>(`/v1/voice/free-voices?lang=${encodeURIComponent(lang)}`),
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
  /** Clonación instantánea con muestras de audio o video (archivos o grabaciones). Gratis; ocupa un espacio. */
  cloneVoice: (opts: { name: string; files: File[]; language: string; description?: string; removeNoise: boolean; consent: boolean }) => {
    const form = new FormData();
    form.append("name", opts.name);
    form.append("language", opts.language);
    form.append("consent", String(opts.consent));
    form.append("remove_background_noise", String(opts.removeNoise));
    if (opts.description) form.append("description", opts.description);
    for (const f of opts.files) form.append("files", f);
    return call<{ voice_id: string; name: string; requires_verification: boolean; sample_seconds: number }>(
      "/v1/voice/clone",
      { method: "POST", body: form },
    );
  },
  designEstimate: (body: VoiceDesignBody) =>
    call<Estimate & { units: number; text: string; voice_quote: string }>("/v1/voice/design/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  designVoice: (body: VoiceDesignBody & { voice_quote: string }) =>
    call<{ previews: VoicePreview[]; text: string; cost_usd: number }>("/v1/voice/design", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  /** URL de una muestra de diseño (`preview_url` relativo a la API). */
  previewUrl: (path: string) => BASE + path,
  saveVoice: (body: { generated_voice_id: string; name: string; description: string; language: string }) =>
    call<{ voice_id: string; name: string }>("/v1/voice/design/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteVoice: (id: string) => call<{ deleted: string }>(`/v1/voice/voices/${id}`, { method: "DELETE" }),
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
  /** Las `limit` más recientes de la biblioteca (o de las ocultas, o de las favoritas). */
  list: (limit = 60, hidden = false, favorite = false, place: { project?: string; folder?: string } = {}) =>
    call<{ generations: Generation[] }>(
      `/v1/generations?limit=${limit}${hidden ? "&hidden=true" : ""}${favorite ? "&favorite=true" : ""}` +
        `${place.project ? `&project=${encodeURIComponent(place.project)}` : ""}${place.folder ? `&folder=${encodeURIComponent(place.folder)}` : ""}`,
    ),
  /** Mueve generaciones a un proyecto y carpeta (null: fuera). */
  move: (ids: string[], projectId: string | null, folderId: string | null = null) =>
    call<{ changed: string[]; skipped: string[] }>("/v1/generations/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, project_id: projectId, folder_id: folderId }),
    }),
  projects: () => call<{ projects: ProjectSummary[] }>("/v1/projects"),
  project: (id: string) => call<Project>(`/v1/projects/${id}`),
  createProject: (name: string, description = "") =>
    call<Project>("/v1/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }) }),
  updateProject: (id: string, patch: { name?: string; description?: string; brief?: string; cover?: string }) =>
    call<Project>(`/v1/projects/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  deleteProject: (id: string) => call<void>(`/v1/projects/${id}`, { method: "DELETE" }),
  createFolder: (projectId: string, name: string) =>
    call<ProjectFolder>(`/v1/projects/${projectId}/folders`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  renameFolder: (id: string, name: string) =>
    call<ProjectFolder>(`/v1/folders/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  deleteFolder: (id: string) => call<void>(`/v1/folders/${id}`, { method: "DELETE" }),
  /** Marca (o desmarca) varias generaciones como favoritas. */
  favorite: (ids: string[], favorite = true) =>
    call<{ changed: string[]; skipped: string[] }>("/v1/generations/favorite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, favorite }),
    }),
  /** Oculta (o vuelve a mostrar) varias generaciones terminadas; las que siguen en curso se saltan. */
  hide: (ids: string[], hidden = true) =>
    call<{ changed: string[]; skipped: string[] }>("/v1/generations/hide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, hidden }),
    }),
  /** Generaciones que esperan aprobación, con su total; las de una corrida de Spaces traen `space_run`. */
  approvals: () => call<{ total: number; generations: PendingApproval[] }>("/v1/approvals"),
  /** Generaciones de cualquiera de esos modelos o cuya entrada contenga alguno de esos textos (historial de una página). */
  find: (filter: { models?: string[]; texts?: string[] }, limit = 100) => {
    const q = new URLSearchParams({ limit: String(limit) });
    for (const m of filter.models ?? []) q.append("model", m);
    for (const t of filter.texts ?? []) q.append("text", t);
    return call<{ generations: Generation[] }>(`/v1/generations?${q}`);
  },
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
  styles: (model: string) => call<{ model: string; styles: ModelStyle[] }>(`/v1/model-styles/${model}`),
  options: (model: string) => call<{ model: string; revision: string | null; categories: LiveCategory[] }>(`/v1/model-options/${model}`),
  /** URL vigente de una salida propia para usarla como entrada de otra generación (gratis). */
  useOutput: (id: string, index = 0, as?: "last_frame" | "audio") =>
    call<{ url: string; kind: string; content_type: string }>(`/v1/generations/${id}/outputs/${index}/use${as ? `?as=${as}` : ""}`, {
      method: "POST",
    }),
  /** 1 a 4 imágenes JPG o PNG (Kling 3.0 pide 2+); `name` en minúsculas (letras, dígitos y _), se cita como @name. */
  /** `urls`: imágenes propias ya subidas (p. ej. una creación vía `useOutput`). */
  createElement: (name: string, description: string, files: File[], urls: string[] = [], category: ElementCategory = "other") => {
    const form = new FormData();
    form.append("name", name);
    form.append("description", description);
    form.append("category", category);
    for (const f of files) form.append("files", f);
    for (const u of urls) form.append("image_urls", u);
    return call<StudioElement>("/v1/elements", { method: "POST", body: form });
  },
  deleteElement: (id: string) => call<void>(`/v1/elements/${id}`, { method: "DELETE" }),
  /** URLs públicas y vigentes de las imágenes de un elemento, para usarlas como referencias en cualquier modelo. */
  elementUrls: (id: string) =>
    call<{ id: string; mention: string; description: string; image_urls: string[] }>(`/v1/elements/${id}/urls`, { method: "POST" }),
  chats: () =>
    call<{ available: boolean; models: string[]; default_model: string; chats: ChatSummary[] }>("/v1/chats"),
  chat: (id: string) => call<Chat>(`/v1/chats/${id}`),
  createChat: (model?: string, projectId: string | null = activeProject()) =>
    call<Chat>("/v1/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...(model ? { model } : {}), ...(projectId ? { project_id: projectId } : {}) }),
    }),
  /** Proyecto del chat ("" lo quita) o tope de la generación automática (0 la apaga). */
  updateChat: (id: string, patch: { project_id?: string; auto_budget_usd?: number }) =>
    call<ChatSummary>(`/v1/chats/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  deleteChat: (id: string) => call<void>(`/v1/chats/${id}`, { method: "DELETE" }),
  /** Anota la generación lanzada desde una propuesta: el agente sabrá cómo terminó. */
  linkProposal: (chatId: string, proposalId: string, jobId: string) =>
    call<ChatProposal>(`/v1/chats/${chatId}/proposals/${proposalId}/job`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    }),
  /** Generación automática: el servidor cotiza, comprueba el tope del chat y lanza lo que falta de la propuesta. */
  autoProposal: (chatId: string, proposalId: string) =>
    call<{ proposal: ChatProposal; auto_spent_usd: number }>(`/v1/chats/${chatId}/proposals/${proposalId}/auto`, { method: "POST" }),
  /** Crea el elemento que propuso AI Director (solo con este clic del usuario). */
  createProposedElement: (chatId: string, proposalId: string) =>
    call<StudioElement>(`/v1/chats/${chatId}/proposals/${proposalId}/element`, { method: "POST" }),
  /** AI Director: lista de tomas del proyecto y sus documentos. */
  shots: (projectId: string) => call<{ shots: Shot[] }>(`/v1/projects/${projectId}/shots`),
  updateShot: (id: string, patch: { status?: ShotStatus; selected_job_id?: string; notes?: string; verdict?: string }) =>
    call<Shot>(`/v1/shots/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  deleteShot: (id: string) => call<void>(`/v1/shots/${id}`, { method: "DELETE" }),
  documents: (projectId: string) => call<{ documents: ProjectDocSummary[] }>(`/v1/projects/${projectId}/documents`),
  document: (id: string) => call<ProjectDoc>(`/v1/documents/${id}`),
  createDocument: (projectId: string, body: { kind: ProjectDocKind; title: string; markdown: string }) =>
    call<ProjectDoc>(`/v1/projects/${projectId}/documents`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateDocument: (id: string, patch: { title?: string; kind?: ProjectDocKind; markdown?: string; base_version: number }) =>
    call<ProjectDoc>(`/v1/documents/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  deleteDocument: (id: string) => call<void>(`/v1/documents/${id}`, { method: "DELETE" }),
  /** Envía un mensaje y entrega cada evento del stream (text, tool, proposal, usage, error, done). */
  skills: () => call<{ skills: SkillSummary[] }>("/v1/skills"),
  skill: (slug: string) => call<Skill>(`/v1/skills/${encodeURIComponent(slug)}`),
  createSkill: (body: SkillBody) =>
    call<Skill>("/v1/skills", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  updateSkill: (slug: string, body: SkillBody) =>
    call<Skill>(`/v1/skills/${encodeURIComponent(slug)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteSkill: (slug: string) => call<void>(`/v1/skills/${encodeURIComponent(slug)}`, { method: "DELETE" }),
  sendChat: async (id: string, body: ChatMessageBody, onEvent: (e: ChatEvent) => void, signal?: AbortSignal) => {
    const res = await fetch(`${BASE}/v1/chats/${id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      // La zona del navegador: el agente sabe qué día y hora es para el usuario.
      body: JSON.stringify({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || undefined, ...body }),
      signal,
    });
    if (!res.ok || !res.body) {
      const err = (await res.json().catch(() => ({}))) as ApiErrorBody;
      throw new StudioError(err.error?.message ?? `Error ${res.status}`, res.status, err.error?.code);
    }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const chunk = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        for (const line of chunk.split("\n")) if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as ChatEvent);
      }
    }
  },
  spaces: () => call<{ spaces: SpaceSummary[] }>("/v1/spaces"),
  space: (id: string) => call<Space>(`/v1/spaces/${id}`),
  createSpace: (title?: string) =>
    call<Space>("/v1/spaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(title ? { title } : {}),
    }),
  /** Guarda con la versión leída; si otra pestaña guardó antes, 409 version_conflict. */
  saveSpace: (id: string, body: { version: number; title?: string; graph?: unknown; cover?: string | null; flow?: Flow | null }) =>
    call<Space>(`/v1/spaces/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteSpace: (id: string) => call<void>(`/v1/spaces/${id}`, { method: "DELETE" }),
  /** Lote (nodo con Lista): `dry_run` cotiza el total; sin él crea todas las generaciones con ese tope. */
  batch: (
    items: { model: string; input: Record<string, unknown>; count: number; hints: Record<string, number> }[],
    opts: { dryRun: true; key?: string } | { dryRun: false; key: string; maxTotalUsd: number | null; maxTotalReserveUsd: number | null; acceptUnknown: boolean },
  ) =>
    call<{ items?: unknown[]; total?: { usd: number; complete: boolean; reserve_usd: number | null }; generations?: Generation[] }>(
      "/v1/generations/batch",
      {
        method: "POST",
        // En seco, la clave de un lote ya empezado hace que el total cuente lo creado con su compromiso de entonces.
        headers: { "Content-Type": "application/json", ...(opts.key ? { "Idempotency-Key": opts.key } : {}) },
        body: JSON.stringify(
          opts.dryRun
            ? { items, dry_run: true }
            : {
                items,
                dry_run: false,
                ...(opts.maxTotalUsd != null ? { max_total_usd: opts.maxTotalUsd } : {}),
                ...(opts.maxTotalReserveUsd != null ? { max_total_reserve_usd: opts.maxTotalReserveUsd } : {}),
                ...(opts.acceptUnknown ? { accept_unknown_cost: true } : {}),
              },
        ),
      },
    ),
  /** Corrida en el servidor: `dry_run` cotiza cada paso; sin él arranca con el tope aprobado. */
  estimateRun: (id: string, body: { mode: "downstream" | "workflow"; node_id?: string; version: number; inputs?: Record<string, unknown> }) =>
    call<RunEstimate>(`/v1/spaces/${id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, dry_run: true }),
    }),
  /** `idempotencyKey`: la misma por diálogo; reintentar tras perder la respuesta devuelve la misma corrida. */
  startRun: (
    id: string,
    body: { mode: "downstream" | "workflow"; node_id?: string; version: number; max_total_usd: number; inputs?: Record<string, unknown> },
    idempotencyKey: string,
  ) =>
    call<SpaceRun>(`/v1/spaces/${id}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    }),
  flows: () => call<{ flows: FlowSummary[] }>("/v1/flows"),
  runs: (id: string, limit = 10) => call<{ runs: SpaceRun[] }>(`/v1/spaces/${id}/runs?limit=${limit}`),
  run: (id: string, runId: string) => call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}`),
  approveRun: (id: string, runId: string, body: { max_total_usd?: number; accept_unknown?: boolean }) =>
    call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cancelRun: (id: string, runId: string) => call<SpaceRun>(`/v1/spaces/${id}/runs/${runId}/cancel`, { method: "POST" }),
  /** Archivos subidos antes (los más recientes primero). */
  uploads: (limit = 60) =>
    call<{ uploads: { id: string; url: string; content_type: string; size: number; filename: string | null; created_at: string }[] }>(`/v1/uploads?limit=${limit}`),
  upload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return call<{ id: string; url: string; content_type: string }>("/v1/uploads", {
      method: "POST",
      body: form,
    });
  },
};

/** Modelo del catálogo que renderiza los cortos de Content Factory. */
export const FACTORY_MODEL = "hf-studio/content-factory";

export type FactoryLayout = "title" | "counter" | "timer" | "map" | "chart" | "comparison" | "list" | "quote" | "scale" | "timeline" | "closing";
export type FactoryItem = { label: string; value?: number; note?: string; lat?: number; lon?: number };
export type FactoryVisual = {
  layout: FactoryLayout;
  headline: string;
  kicker?: string;
  value?: number;
  from_value?: number;
  unit?: string;
  prefix?: string;
  items: FactoryItem[];
};
export type FactoryScene = { narration: string; visual: FactoryVisual };
/** Guion de un episodio (lo que recibe `hf-studio/content-factory` en `script`). */
export type FactoryScript = {
  title: string;
  hook?: string;
  scenes: FactoryScene[];
  cliffhanger?: string;
  episode?: number;
  episodes?: number;
  series_title?: string;
};
export type FactoryStyle = {
  id: string;
  name: string;
  names: { es: string; en: string };
  description: string;
  descriptions: { es: string; en: string };
  colors: string[];
  preview: string;
};
export type FactoryInfo = {
  model: string;
  styles: FactoryStyle[];
  layouts: FactoryLayout[];
  max_episodes: number;
  renderer: { available: boolean; reason: string | null };
  scripts: { available: boolean; model: string };
  elevenlabs: boolean;
};
export type FactoryScripts = {
  series_title: string;
  episodes: FactoryScript[];
  cost_usd: number;
  usage: { input_tokens: number; output_tokens: number };
  model: string;
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

/** Supercomputer: chats con el agente que aclara la idea y propone generaciones. */
export type ChatSummary = {
  id: string;
  title: string;
  model: string;
  cost_usd: number;
  created_at: string;
  updated_at: string;
  project_id?: string | null;
  /** Tope de la generación automática (null: apagada) y lo ya lanzado con ella. */
  auto_budget_usd?: number | null;
  auto_spent_usd?: number;
};
export type ChatProposal = {
  tool_use_id: string;
  model: string;
  model_title: string;
  output: "video" | "image";
  title: string;
  input: Record<string, unknown>;
  estimate: {
    usd: number | null;
    kind: string | null;
    provider: string | null;
    reserve_usd: number | null;
    missing: string[] | null;
    /** Con variaciones: precio de una; `usd` es el total. */
    unit_usd?: number | null;
  };
  job_id: string | null;
  /** Variaciones: cuántas generaciones lanza la tarjeta, la entrada de cada una y las ya lanzadas. */
  variations?: number;
  inputs?: Record<string, unknown>[];
  /** Varias piezas distintas (`items`): el título de cada una. Vacío en variaciones. */
  labels?: string[];
  job_ids?: string[];
  /** Toma de la lista a la que va cada posición (AI Director). */
  shots?: ({ shot_id: string; role: "take" | "board" } | null)[];
  /** `element`: tarjeta para crear un elemento desde generaciones (no genera nada). */
  kind?: "element";
  name?: string;
  category?: string;
  description?: string;
  previews?: { url: string; kind: "image" | "video"; frame: "first" | "last" | null }[];
  element_id?: string | null;
};
export type ShotStatus = "planned" | "boarded" | "proposed" | "generating" | "review" | "approved" | "retake" | "cut";
export type ShotTake = { job_id: string; status: string; kind: "image" | "video" | null; url: string | null; file_url: string | null; cost_usd: number | null };
export type Shot = {
  id: string;
  project_id: string;
  scene: string;
  number: string;
  order: number;
  purpose: string;
  shot_size: string | null;
  duration_s: number | null;
  screen_direction: string;
  element_ids: string[];
  model_id: string | null;
  params: Record<string, unknown>;
  prompt: string;
  notes: string;
  status: ShotStatus;
  board_job_id: string | null;
  take_job_ids: string[];
  selected_job_id: string | null;
  verdict: string;
  start_frame_url: string | null;
  updated_at: string;
  takes: ShotTake[];
  board: ShotTake | null;
  selected: ShotTake | null;
};
export type ProjectDocKind = "treatment" | "breakdown" | "bible" | "lookbook" | "color_script" | "blocking" | "script" | "notes" | "other";
export type ProjectDocSummary = {
  id: string;
  project_id: string;
  kind: ProjectDocKind;
  title: string;
  version: number;
  updated_by: "agent" | "user";
  chars: number;
  excerpt: string;
  updated_at: string;
};
export type ProjectDoc = ProjectDocSummary & { markdown: string };
export type SkillSummary = { slug: string; description: string; updated_at: string; files: { path: string; chars: number }[] };
export type Skill = SkillSummary & { body: string };
export type SkillBody = ({ slug: string; description: string; body: string } | { skill_md: string }) & { files?: Record<string, string> };
export type ChatQuestion = { id: string; question: string; options: { label: string; detail?: string }[] };
export type ChatPart =
  | { type: "text"; text: string }
  | { type: "proposal"; proposal: ChatProposal }
  | { type: "question"; question: ChatQuestion }
  | { type: "sources"; sources: { url: string; title: string }[] };
export type ChatMessage = { role: "user"; text: string; attachments: string[]; documents?: string[] } | { role: "assistant"; parts: ChatPart[] };
export type Chat = ChatSummary & { messages: ChatMessage[] };
export type ChatMode = "ask" | "auto";
export type ChatMessageBody = {
  text: string;
  mode: ChatMode;
  model?: string;
  effort?: "low" | "medium" | "high";
  attachments?: { url: string; content_type?: string | null; filename?: string | null }[];
  /** Archivos de texto (.md, .txt) que viajan con el mensaje. */
  documents?: { name: string; content: string }[];
};
export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool"; name: string; label: "searching" | "reading" | "proposing" | string }
  | { type: "proposal"; proposal: ChatProposal }
  | { type: "question"; question: ChatQuestion }
  | { type: "usage"; cost_usd: number }
  | { type: "error"; message: string }
  | { type: "done"; chat: Chat };
