export type JSONSchema = {
  type?: string | string[];
  enum?: (string | number)[];
  const?: unknown;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  format?: string;
  title?: string;
  description?: string;
  items?: JSONSchema;
  properties?: Record<string, JSONSchema>;
  required?: string[];
  if?: JSONSchema;
  then?: JSONSchema;
  else?: JSONSchema;
};

export type ModelSummary = {
  id: string;
  title: string;
  output: "video" | "image" | "audio" | "text" | "unknown";
  workflow: string;
  family: string;
  capabilities: string[];
  docs_url: string;
  /** Tipos que aceptan sus puertos (prompt = text, campos *_url = image, video o audio). */
  inputs?: ("text" | "image" | "video" | "audio")[];
  /** Solo lo venden las tiendas (APIMart, KIE), no Higgsfield. */
  store?: boolean;
};

export type ModelDetail = ModelSummary & {
  summary: string;
  notes: string[];
  input_schema: JSONSchema;
  /** La API acepta keep_source_audio (video de origen cuyo audio el modelo no conserva solo). */
  keep_source_audio?: boolean;
};

export type Output = {
  kind: string;
  url: string;
  content_type?: string | null;
  file_url?: string;
  /** Resultado de conservar el audio de origen: source | source_has_no_audio | mux_failed. */
  audio?: string;
};

export type JobStatus =
  | "pending"
  | "submitting"
  | "queued"
  | "in_progress"
  | "completed"
  | "failed"
  | "nsfw"
  | "canceled"
  | "timed_out"
  | "awaiting_approval";

export type Generation = {
  id: string;
  model: string;
  status: JobStatus;
  stage: string;
  terminal: boolean;
  input: Record<string, unknown>;
  keep_source_audio?: boolean;
  outputs: Output[];
  error: string | null;
  error_kind: string | null;
  request_id: string | null;
  created_at: string;
  finished_at: string | null;
  elapsed_seconds: number;
  deduplicated?: boolean;
  /** Cliente que la lanzó; solo llega a clientes que ven todo (la UI). */
  source?: string;
  /** Proveedor que la ejecuta (higgsfield, apimart, kie…), su precio y lo aprobado. */
  provider?: string;
  /** Id del modelo en ese proveedor (el canal exacto) y si es un canal oficial. */
  provider_model?: string | null;
  official?: boolean;
  /** Precio cotizado de la opción en curso: al completarse, lo que costó (aproximado si cost_kind es approx). */
  cost_usd?: number | null;
  cost_kind?: string | null;
  max_usd?: number | null;
  max_reserve_usd?: number | null;
  reserve_usd?: number | null;
  plan?: { provider: string; model?: string | null; official?: boolean; usd: number | null; kind?: string | null; reserve_usd?: number | null }[];
  attempts?: { provider: string; error_kind: string | null; error: string | null; at: string }[];
  /** Oculta del historial y de los listados (solo se ve en /history/hidden). */
  hidden?: boolean;
  /** Marcada como favorita (filtro «Favoritas» de la biblioteca). */
  favorite?: boolean;
};

export type ProviderInfo = {
  name: string;
  title: string;
  env_var: string;
  configured: boolean;
  required: boolean;
  signup_url: string;
  key_url: string;
  billing_url: string | null;
  docs_url: string | null;
  blurb: string;
  valid?: boolean | null;
  balance_usd?: number | null;
  message?: string | null;
};

/** Gasto de las generaciones terminadas (GET /v1/usage): precio cotizado, no el cobro conciliado. */
export type UsageGroup = { usd: number; generations: number; unpriced: number };
export type Usage = {
  since: string | null;
  total_usd: number;
  approx_usd: number;
  generations: number;
  unpriced: number;
  providers: (UsageGroup & { provider: string })[];
  models: (UsageGroup & { model: string; provider: string })[];
  days: { date: string; usd: number }[];
};

export type ApiErrorBody = {
  error?: { code: string; message: string; details?: { path: string; message: string }[] };
};

export type PresetVariable = {
  key: string;
  label: string;
  type: "text" | "textarea" | "select" | "image" | "images" | "video" | "number";
  required?: boolean;
  default?: unknown;
  options?: string[];
  placeholder?: string;
};

export type Preset = {
  slug: string;
  title: string;
  description: string;
  category: string;
  output: "video" | "image";
  model: string;
  template: Record<string, unknown>;
  variables: PresetVariable[];
  cover: string | null;
  builtin: boolean;
};

export type Voice = {
  voice_id: string;
  name: string;
  public_owner_id: string | null;
  preview_url: string | null;
  description: string | null;
  labels: Record<string, string>;
  library: boolean;
};

/** Voz gratis de edge-tts (voces neuronales de Microsoft Edge). */
export type FreeVoice = {
  voice_id: string;
  name: string;
  locale: string;
  country: string;
  gender: string;
  personalities: string[];
  multilingual: boolean;
};

export type VoiceStatus = {
  configured: boolean;
  tier?: string | null;
  credits_left?: number | null;
  credits_limit?: number | null;
};

export type VoiceEffect = "none" | "deep" | "monster" | "ghost";

export type VoiceChangeBody = {
  source_generation_id?: string;
  source_url?: string;
  start: number;
  end?: number;
  voice_id: string;
  voice_name?: string;
  public_owner_id?: string;
  effect: VoiceEffect;
  original_volume: number;
  remove_background_noise: boolean;
  /** Cotización de /v1/voice/estimate para esta misma petición (un solo uso): sin ella la API no gasta. */
  voice_quote?: string;
};

export type Sound = {
  id: string;
  job_id: string | null;
  origin: "studio" | "elevenlabs";
  kind: "speech" | "voice_change" | "sound_effect" | "music" | "isolated";
  title: string;
  category: string;
  tags: string[];
  text: string;
  duration: number | null;
  file_url: string;
  created_at: string;
  source?: string;
};

/** Elemento de HF Studio para Kling 3.0 (APIMart y KIE): se cita en el prompt con `mention` (@nombre). */
/** Un estilo del catálogo de un modelo (Genjutsu Restyle): su `id` va en `preset_id`. */
export type ModelStyle = { id: string; name: string; preview_url: string | null };

export type StudioElement = {
  id: string;
  name: string;
  description: string;
  mention: string;
  /** Rutas de la API (/v1/elements/{id}/images/{n}); en el navegador van por el proxy. */
  images: string[];
  created_at: string;
};
