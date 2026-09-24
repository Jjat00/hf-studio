import type { ApiErrorBody, Generation, ModelDetail, ModelSummary } from "./types";

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
  return res.json() as Promise<T>;
}

export const studio = {
  models: (params: Record<string, string> = {}) =>
    call<{ synced_at: string; capabilities: string[]; models: ModelSummary[] }>(
      `/v1/models?${new URLSearchParams(params)}`,
    ),
  model: (id: string) => call<ModelDetail>(`/v1/models/${id}`),
  estimate: (model: string, input: Record<string, unknown>) =>
    call<Estimate>("/v1/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, input }),
    }),
  generate: (model: string, input: Record<string, unknown>, idempotencyKey: string) =>
    call<Generation>("/v1/generations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ model, input }),
    }),
  list: (limit = 60) => call<{ generations: Generation[] }>(`/v1/generations?limit=${limit}`),
  get: (id: string) => call<Generation>(`/v1/generations/${id}`),
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

/** Higgsfield devuelve o un costo fijo o, en modelos medidos por tokens, solo la fórmula de precio. */
export type Estimate =
  | { type: "estimate"; credits: string; usd: string }
  | { type: "description"; pricing_description: string };

const SHORT_SIDE: Record<string, number> = { "480p": 480, "720p": 720, "1080p": 1080, "4k": 2160 };

/**
 * Etiqueta corta para el botón Generate. Para precios por tokens de video aplica la fórmula
 * publicada (segundos × ancho × alto × 24 fps / 1024 tokens) y devuelve un aproximado en USD.
 */
export function estimateLabel(e: Estimate, input: Record<string, unknown>): { text: string; hint?: string } | null {
  if (e.type === "estimate") {
    const credits = parseFloat(e.credits);
    return Number.isFinite(credits) ? { text: String(credits), hint: `≈ $${e.usd}` } : null;
  }
  const d = e.pricing_description;
  const rates = d.match(/480p\/720p\/1080p \$([\d.]+),\s*4K \$([\d.]+)/i);
  if (!/video tokens/i.test(d) || !rates) return { text: "?", hint: d };
  const res = String(input.resolution ?? "720p").toLowerCase();
  const seconds = Number(input.duration ?? 5);
  const parts = String(input.aspect_ratio ?? "16:9").split(":").map(Number);
  const [a, b] = parts.length === 2 && parts.every((n) => n > 0) ? parts : [16, 9];
  const short = SHORT_SIDE[res] ?? 720;
  const long = (short * Math.max(a, b)) / Math.min(a, b);
  const tokens = Math.ceil((seconds * short * long * 24) / 1024);
  const rate = parseFloat(res === "4k" ? rates[2] : rates[1]);
  const usd = (tokens / 1000) * rate;
  return { text: `~$${usd.toFixed(2)}`, hint: d };
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
