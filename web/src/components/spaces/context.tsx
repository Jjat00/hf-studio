"use client";

import type { Edge } from "@xyflow/react";
import { createContext, use } from "react";
import type { GeneratorData, ListData, MediaData, NoteData, RunNodeState, TextData } from "@/lib/spaces";
import type { Estimate } from "@/lib/studio";
import type { Generation, ModelDetail, ModelSummary } from "@/lib/types";

/** `confirm`/`confirmRequest`: firma y petición exacta cuyo precio desconocido pidió confirmación. */
export type RunState = { busy?: boolean; error?: string | null; confirm?: string | null; confirmRequest?: string | null };
/** Cotización de un nodo: `key` es la firma del lienzo y `request` la petición resuelta que se cotizó. */
export type NodeEstimate = { key: string; request?: string; value: Estimate | null; error?: string };

/** Estado del lienzo que los nodos leen: catálogo, trabajos, costos y acciones. El grafo vive en React Flow. */
export type SpaceCtx = {
  models: Map<string, ModelSummary>;
  details: Record<string, ModelDetail>;
  jobs: Record<string, Generation>;
  /** Trabajos que ya no existen (borrados del historial). */
  gone: Set<string>;
  edges: Edge[];
  /** Firma actual de las entradas de cada generador: si coincide con la de su cotización, el precio vale. */
  signatures: Record<string, string>;
  estimates: Record<string, NodeEstimate>;
  runStates: Record<string, RunState>;
  run: (nodeId: string) => void;
  /** Mezcla `patch` en los datos del nodo (texto, medio, generador o lista). */
  update: (nodeId: string, patch: Partial<TextData & NoteData & GeneratorData> & Partial<MediaData | ListData>) => void;
  /** Cambia un ajuste del generador sobre su estado más reciente (dos cambios seguidos no se pisan). */
  setValue: (nodeId: string, key: string, value: unknown) => void;
  changeModel: (nodeId: string, model: string) => void;
  /** Corrida en el servidor desde este nodo (él y lo que depende de él). */
  runFrom: (nodeId: string) => void;
  /** Estado de cada nodo en la corrida activa. */
  runNodes: Record<string, RunNodeState>;
  runBusy: boolean;
};

export const SpaceContext = createContext<SpaceCtx | null>(null);

export function useSpace() {
  const ctx = use(SpaceContext);
  if (!ctx) throw new Error("useSpace outside SpaceContext");
  return ctx;
}

export function selectedRun(data: GeneratorData): string | undefined {
  if (!data.runs.length) return undefined;
  const i = data.selected ?? data.runs.length - 1;
  return data.runs[Math.min(Math.max(i, 0), data.runs.length - 1)];
}
