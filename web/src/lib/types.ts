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
  outputs: Output[];
  error: string | null;
  error_kind: string | null;
  request_id: string | null;
  created_at: string;
  finished_at: string | null;
  elapsed_seconds: number;
  deduplicated?: boolean;
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
