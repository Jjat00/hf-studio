import type { Edge, Node } from "@xyflow/react";
import { fieldsFor, type Field } from "./schema";
import type { JSONSchema, ModelDetail } from "./types";

/** Tipos de dato que viajan por las conexiones; cada uno con su color, como en Magnific Spaces. */
/** Corridas guardadas por nodo (mismo límite que la API). */
export const MAX_RUNS = 200;

export type PortKind = "text" | "image" | "video" | "audio";
export const KIND_COLOR: Record<PortKind, string> = {
  text: "#60a5fa",
  image: "#a78bfa",
  video: "#4ade80",
  audio: "#fb923c",
};

export type TextData = { text: string };
export type NoteData = { text: string };
export type MediaData = { url?: string; kind?: "image" | "video" | "audio"; name?: string };
/** `values`: ajustes propios del nodo (los campos conectados los pone la arista). `runs`: ids de trabajos. */
export type GeneratorData = { model: string; values: Record<string, unknown>; runs: string[]; selected?: number };

export type TextNode = Node<TextData, "text">;
export type NoteNode = Node<NoteData, "note">;
export type MediaNode = Node<MediaData, "media">;
export type GeneratorNode = Node<GeneratorData, "generator">;
export type SpaceNode = TextNode | NoteNode | MediaNode | GeneratorNode;

export type SpaceGraph = { nodes: SpaceNode[]; edges: Edge[]; viewport: { x: number; y: number; zoom: number } };

export type SpaceSummary = {
  id: string;
  title: string;
  cover: string | null;
  version: number;
  nodes: number;
  created_at: string;
  updated_at: string;
};
export type Space = SpaceSummary & { graph: SpaceGraph };

/** Puerto de entrada de un generador: el prompt o un campo de medios del `input_schema`. */
export type InPort = { key: string; kind: PortKind; multiple: boolean; max: number; required: boolean };

export function inPorts(detail: ModelDetail): InPort[] {
  const ports: InPort[] = [];
  for (const f of fieldsFor(detail.input_schema, detail.id)) {
    if (f.kind === "prompt") ports.push({ key: f.key, kind: "text", multiple: true, max: 8, required: f.required });
    if (f.kind === "media") ports.push({ key: f.key, kind: f.media, multiple: f.multiple, max: f.max, required: f.required });
  }
  return ports;
}

/** Campos que se ajustan en el inspector (los de medios y el prompt van por puertos). */
export function settingFields(detail: ModelDetail) {
  return fieldsFor(detail.input_schema, detail.id).filter(
    (f): f is Exclude<Field, { kind: "prompt" } | { kind: "media" }> => f.kind !== "prompt" && f.kind !== "media",
  );
}

export function mediaFields(detail: ModelDetail) {
  return fieldsFor(detail.input_schema, detail.id).filter((f): f is Extract<Field, { kind: "media" }> => f.kind === "media");
}

/** Lo que sale de un nodo: texto, el medio que contiene o lo que genera su modelo. */
export function outKind(node: SpaceNode | undefined, outputOf: (model: string) => string | undefined): PortKind | null {
  if (!node) return null;
  if (node.type === "text") return "text";
  if (node.type === "media") return node.data.kind ?? null;
  if (node.type === "generator") {
    const o = outputOf(node.data.model);
    return o === "image" || o === "video" || o === "audio" ? o : null;
  }
  return null;
}

export function kindOfUrl(contentType: string): "image" | "video" | "audio" | null {
  if (contentType.startsWith("image/")) return "image";
  if (contentType.startsWith("video/")) return "video";
  if (contentType.startsWith("audio/")) return "audio";
  return null;
}

/** Aristas que entran a un nodo, agrupadas por campo y en el orden en que se conectaron. */
export function incoming(edges: Edge[], nodeId: string): Map<string, Edge[]> {
  const map = new Map<string, Edge[]>();
  for (const e of edges) {
    if (e.target !== nodeId || !e.targetHandle) continue;
    map.set(e.targetHandle, [...(map.get(e.targetHandle) ?? []), e]);
  }
  return map;
}

/** ¿Hay un camino de `from` a `to`? Evita conexiones que formen un ciclo. */
export function reaches(edges: Edge[], from: string, to: string): boolean {
  const stack = [from];
  const seen = new Set<string>();
  while (stack.length) {
    const id = stack.pop()!;
    if (id === to) return true;
    if (seen.has(id)) continue;
    seen.add(id);
    for (const e of edges) if (e.source === id) stack.push(e.target);
  }
  return false;
}

/** Grafo listo para guardar: sin estado de vista de React Flow (selección, medidas, arrastre). */
export function serialize(nodes: SpaceNode[], edges: Edge[], viewport: SpaceGraph["viewport"]) {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      data: n.data,
      ...(n.width ? { width: n.width } : {}),
      ...(n.height ? { height: n.height } : {}),
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? "out",
      targetHandle: e.targetHandle,
    })),
    viewport,
  };
}

/** ¿El valor cumple el tipo de su campo? Los controles del inspector asumen ese tipo (revisión 52). */
export function fits(schema: JSONSchema | undefined, value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (!schema) return false;
  if (schema.enum) return schema.enum.includes(value as string | number);
  const types = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
  if (!types.length) return true;
  return types.some((t) => {
    if (t === "array") return Array.isArray(value) && value.every((x) => fits(schema.items, x));
    if (t === "object") return typeof value === "object" && !Array.isArray(value);
    if (t === "integer") return Number.isInteger(value);
    if (t === "number") return typeof value === "number";
    return typeof value === t;
  });
}

/** Ajustes del nodo que encajan con el esquema de su modelo; lo que no encaja se ignora. */
export function validValues(detail: ModelDetail, values: Record<string, unknown>) {
  const props = detail.input_schema.properties ?? {};
  return Object.fromEntries(Object.entries(values).filter(([k, v]) => fits(props[k], v)));
}

/** Defensa al abrir un grafo guardado: los campos que la UI lee siempre existen. */
export function normalizeNode(n: SpaceNode): SpaceNode {
  const data = (n.data ?? {}) as Record<string, unknown>;
  if (n.type === "generator")
    return { ...n, data: { ...n.data, values: (data.values as Record<string, unknown>) ?? {}, runs: Array.isArray(data.runs) ? (data.runs as string[]) : [] } };
  if (n.type === "text" || n.type === "note") return { ...n, data: { ...n.data, text: typeof data.text === "string" ? data.text : "" } } as SpaceNode;
  return n;
}

/** Herramientas locales de HF Studio (fotograma, combinar, mezclar): modelos propios y gratis. */
export function isTool(modelId: string) {
  return modelId.startsWith("hf-studio/");
}

/** Nodos de audio de ElevenLabs para Spaces (voz, efecto, música). */
export function isAudioNode(modelId: string) {
  return modelId === "elevenlabs/tts" || modelId === "elevenlabs/sfx" || modelId === "elevenlabs/music-gen";
}

export function newId(prefix: string) {
  return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
}

/** Paso de una corrida cotizada en seco: `later` se cotiza al llegar (depende de otro paso de la corrida). */
export type RunStep = {
  node_id: string;
  model: string;
  status: "ok" | "unknown" | "later" | "error";
  usd?: number | null;
  reserve_usd?: number | null;
  provider?: string;
  error?: string;
};
export type RunEstimate = { steps: RunStep[]; total_usd: number; reserve_usd: number; pending: number };

export type RunNodeState = {
  status: "pending" | "running" | "done" | "failed" | "skipped" | "canceled";
  job_id?: string;
  usd?: number | null;
  reserve_usd?: number | null;
  error?: string;
  waiting?: boolean;
  spend?: number;
};
export type SpaceRun = {
  id: string;
  space_id: string;
  mode: "downstream" | "workflow";
  start_node: string | null;
  status: "running" | "awaiting_approval" | "completed" | "partial" | "failed" | "canceled";
  order: string[];
  nodes: Record<string, RunNodeState>;
  max_total_usd: number;
  committed_usd: number;
  pause: {
    node: string;
    reason: "over_budget" | "unknown_cost" | "job_approval";
    usd?: number | null;
    reserve_usd?: number | null;
    needed_total_usd?: number;
    job_id?: string;
    unknown?: boolean;
  } | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};
export const RUN_ACTIVE = ["running", "awaiting_approval"];
