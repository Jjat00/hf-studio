"use client";

import type { Edge } from "@xyflow/react";
import { useCallback, useEffect, useRef } from "react";
import { MAX_RUNS, newId, type SpaceNode } from "@/lib/spaces";

/** Estado del lienzo que se puede deshacer: nodos (sin estado de vista) y aristas. */
type Snapshot = { nodes: SpaceNode[]; edges: Edge[]; key: string };

const MAX_HISTORY = 100;
const SETTLE_MS = 400;

/** Lo que cuenta como cambio: posición, tipo y datos, sin las corridas ni la corrida elegida (que llegan del
 * servidor y no se deshacen) ni la selección o las medidas de React Flow. */
function keyOf(nodes: SpaceNode[], edges: Edge[]) {
  return JSON.stringify([
    nodes.map((n) => {
      const data = n.type === "generator" ? { ...n.data, runs: undefined, selected: undefined } : n.data;
      return [n.id, n.type, Math.round(n.position.x), Math.round(n.position.y), data];
    }),
    edges.map((e) => [e.id, e.source, e.sourceHandle ?? "out", e.target, e.targetHandle]),
  ]);
}

function clean(nodes: SpaceNode[]): SpaceNode[] {
  return nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data }) as SpaceNode);
}

function editing(target: EventTarget | null) {
  const el = target instanceof Element ? target : null;
  return !!el?.closest("input, textarea, select, [contenteditable=true]");
}

/**
 * Deshacer y rehacer (Ctrl+Z, Ctrl+Shift+Z o Ctrl+Y), copiar, pegar y duplicar nodos (Ctrl+C, Ctrl+V,
 * Ctrl+D), como en Magnific. La historia guarda el lienzo cuando se asienta (no cada píxel de un arrastre).
 * Al deshacer, un generador conserva sus corridas más recientes: un trabajo pagado nunca desaparece del nodo.
 */
export function useCanvasEdit({
  nodes,
  edges,
  setNodes,
  setEdges,
}: {
  nodes: SpaceNode[];
  edges: Edge[];
  setNodes: (fn: (ns: SpaceNode[]) => SpaceNode[]) => void;
  setEdges: (fn: (es: Edge[]) => Edge[]) => void;
}) {
  const current = useRef<Snapshot>({ nodes: clean(nodes), edges, key: keyOf(nodes, edges) });
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const clipboard = useRef<{ nodes: SpaceNode[]; edges: Edge[]; pastes: number } | null>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  // Corridas vigentes de cada generador por id, aunque el nodo se borre: al deshacer o rehacer, un nodo vuelve
  // con su historial más reciente, nunca con el de un snapshot viejo (revisión 76).
  const runsById = useRef(new Map<string, { runs: string[]; selected?: number }>());
  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
    for (const n of nodes) if (n.type === "generator") runsById.current.set(n.id, { runs: n.data.runs, selected: n.data.selected });
  }, [nodes, edges]);

  // Registra el lienzo cuando deja de cambiar (y nadie arrastra un nodo).
  useEffect(() => {
    if (nodes.some((n) => n.dragging)) return;
    const timer = setTimeout(() => {
      const key = keyOf(nodes, edges);
      if (key === current.current.key) return;
      past.current = [...past.current, current.current].slice(-MAX_HISTORY);
      future.current = [];
      current.current = { nodes: clean(nodes), edges, key };
    }, SETTLE_MS);
    return () => clearTimeout(timer);
  }, [nodes, edges]);

  /** Registra generaciones nuevas de un nodo aunque ya no esté en el lienzo (respuesta tardía tras borrarlo):
   * deshacer el borrado lo devuelve con ellas (revisión 77). */
  const recordRuns = useCallback((nodeId: string, jobIds: string[]) => {
    const prev = runsById.current.get(nodeId) ?? { runs: [] };
    // Misma política que los nodos presentes (`mergeRun`): sin duplicados y con el tope de corridas de la API.
    const runs = [...prev.runs, ...jobIds.filter((j) => !prev.runs.includes(j))].slice(0, MAX_RUNS);
    if (runs.length !== prev.runs.length) runsById.current.set(nodeId, { runs, selected: runs.length - 1 });
  }, []);

  /** Lleva a la historia, ya, un cambio que aún no se asentó: deshacer parte del lienzo que se ve (revisión 76). */
  const flush = useCallback(() => {
    const key = keyOf(nodesRef.current, edgesRef.current);
    if (key === current.current.key) return;
    past.current = [...past.current, current.current].slice(-MAX_HISTORY);
    future.current = [];
    current.current = { nodes: clean(nodesRef.current), edges: edgesRef.current, key };
  }, []);

  const restore = useCallback(
    (snap: Snapshot) => {
      const ids = new Set(snap.nodes.map((n) => n.id));
      const restored = snap.nodes.map((n) => {
        const live = n.type === "generator" ? runsById.current.get(n.id) : undefined;
        // Las corridas no se deshacen: el nodo vuelve con las más recientes que tuvo.
        if (!live) return n;
        const runs = live.runs.slice(0, MAX_RUNS);
        const selected = live.selected === undefined || !runs.length ? undefined : Math.min(live.selected, runs.length - 1);
        return { ...n, data: { ...n.data, runs, selected } } as SpaceNode;
      });
      // Solo aristas entre nodos que existen en el estado restaurado.
      const links = snap.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
      snap = { ...snap, edges: links };
      current.current = { nodes: clean(restored), edges: snap.edges, key: keyOf(restored, snap.edges) };
      setNodes(() => restored);
      setEdges(() => snap.edges);
    },
    [setNodes, setEdges],
  );

  const undo = useCallback(() => {
    flush();
    const prev = past.current.at(-1);
    if (!prev) return;
    past.current = past.current.slice(0, -1);
    future.current = [current.current, ...future.current];
    restore(prev);
  }, [restore, flush]);

  const redo = useCallback(() => {
    flush();
    const next = future.current[0];
    if (!next) return;
    future.current = future.current.slice(1);
    past.current = [...past.current, current.current];
    restore(next);
  }, [restore, flush]);

  /** Copia de los nodos seleccionados y de las conexiones entre ellos, con ids nuevos y sin corridas. */
  const place = useCallback(
    (source: { nodes: SpaceNode[]; edges: Edge[] }, offset: number) => {
      const ids = new Map(source.nodes.map((n) => [n.id, newId(n.type === "generator" ? "gen" : n.type)]));
      const copies = source.nodes.map((n) => {
        const data = n.type === "generator" ? { ...n.data, runs: [], selected: undefined } : { ...n.data };
        return { ...n, id: ids.get(n.id)!, position: { x: n.position.x + offset, y: n.position.y + offset }, data, selected: true } as SpaceNode;
      });
      const links = source.edges.map((e) => ({ ...e, id: newId("e"), source: ids.get(e.source)!, target: ids.get(e.target)! }));
      setNodes((ns) => [...ns.map((n) => (n.selected ? ({ ...n, selected: false } as SpaceNode) : n)), ...copies]);
      setEdges((es) => [...es, ...links]);
    },
    [setNodes, setEdges],
  );

  const selection = useCallback(() => {
    const picked = nodesRef.current.filter((n) => n.selected);
    const ids = new Set(picked.map((n) => n.id));
    return { nodes: clean(picked), edges: edgesRef.current.filter((e) => ids.has(e.source) && ids.has(e.target)) };
  }, []);

  const copy = useCallback(() => {
    const sel = selection();
    if (sel.nodes.length) clipboard.current = { ...sel, pastes: 0 };
  }, [selection]);

  const paste = useCallback(() => {
    const clip = clipboard.current;
    if (!clip) return;
    clip.pastes += 1;
    place(clip, 40 * clip.pastes);
  }, [place]);

  const duplicate = useCallback(
    (nodeId?: string) => {
      if (nodeId) {
        const n = nodesRef.current.find((x) => x.id === nodeId);
        if (n) place({ nodes: clean([n]), edges: [] }, 40);
        return;
      }
      const sel = selection();
      if (sel.nodes.length) place(sel, 40);
    },
    [place, selection],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || editing(e.target)) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) undo();
      else if ((k === "z" && e.shiftKey) || k === "y") redo();
      else if (k === "c") copy();
      else if (k === "v") paste();
      else if (k === "d") duplicate();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, copy, paste, duplicate]);

  return { undo, redo, duplicate, recordRuns };
}
