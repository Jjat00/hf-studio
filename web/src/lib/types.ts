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
  output: "video" | "image" | "audio" | "unknown";
  workflow: string;
  family: string;
  capabilities: string[];
  docs_url: string;
};

export type ModelDetail = ModelSummary & {
  summary: string;
  notes: string[];
  input_schema: JSONSchema;
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
  | "timed_out";

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
