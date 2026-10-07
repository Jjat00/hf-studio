"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type NodeTypes,
  type OnConnectEnd,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import clsx from "clsx";
import { AlertTriangle, Check, ChevronLeft, CloudOff, ImageIcon, Loader2, Maximize, Play, Plus, Share2, StickyNote, Type, Upload, Video } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { ModelPicker } from "@/components/studio/model-picker";
import { probeDuration } from "@/lib/media";
import { cleanInput, defaultsFor } from "@/lib/schema";
import {
  incoming,
  inPorts,
  KIND_COLOR,
  mediaFields,
  isAssistant,
  isDerived,
  isTool,
  listValues,
  MAX_RUNS,
  splitStep,
  newId,
  RUN_ACTIVE,
  type RunEstimate,
  type SpaceRun,
  normalizeNode,
  outKind,
  reaches,
  serialize,
  type Flow,
  type GeneratorNode,
  type ListNode,
  type PortKind,
  type Space,
  type SpaceGraph,
  type SpaceNode,
} from "@/lib/spaces";
import { fieldErrors, formatUsd, modelLabel, outputSrc, studio, StudioError, type Estimate } from "@/lib/studio";
import type { Generation, ModelDetail, ModelSummary } from "@/lib/types";
import { AddMenu, type AddChoice } from "./add-menu";
import { SpaceContext, selectedRun, type NodeEstimate, type RunState, type SpaceCtx } from "./context";
import { Inspector } from "./inspector";
import { PublishDialog } from "./publish-dialog";
import { RunBanner, RunDialog } from "./run-panel";
import { GeneratorNodeView, ListNodeView, MediaNodeView, NoteNodeView, portLabel, TextNodeView } from "./nodes";

const NODE_TYPES: NodeTypes = { text: TextNodeView, media: MediaNodeView, generator: GeneratorNodeView, note: NoteNodeView, list: ListNodeView };
const POLL_MS = 2500;
const SAVE_DELAY_MS = 900;

const detailCache = new Map<string, Promise<ModelDetail>>();
function loadDetail(id: string) {
  if (!detailCache.has(id)) {
    const p = studio.model(id);
    p.catch(() => detailCache.delete(id));
    detailCache.set(id, p);
  }
  return detailCache.get(id)!;
}

/** Error de entradas (falta conectar algo, un paso previo sin generar): se muestra tal cual en el nodo. */
class InputError extends Error {}

type XY = { x: number; y: number };
/** `exact`: el nodo va justo donde se hizo clic (sin buscar hueco). */
type Menu = { at: XY; flowAt: XY; from: { nodeId: string; kind: PortKind; handle: string } | null; exact?: boolean };

export function SpaceEditor({ id }: { id: string }) {
  const { t } = useI18n();
  const [space, setSpace] = useState<Space | null>(null);
  const [models, setModels] = useState<ModelSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    studio.space(id).then(setSpace, (e) => setError(e instanceof Error ? e.message : String(e)));
  }, [id, reloads]);
  useEffect(() => {
    studio.models().then(
      (r) => setModels(r.models),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, []);

  if (error) {
    return (
      <div className="mx-auto flex max-w-lg flex-col items-center gap-3 p-12 text-center">
        <AlertTriangle className="size-6 text-danger" />
        <p className="text-danger">{error}</p>
        <Link href="/spaces" className="text-sm text-lime hover:underline">
          {t.spaces.back}
        </Link>
      </div>
    );
  }
  if (!space || !models) return <div className="shimmer m-3 h-[calc(100dvh-80px)] rounded-panel" />;
  return (
    <ReactFlowProvider key={`${space.id}:${reloads}`}>
      <Canvas
        space={space}
        models={models}
        onReload={() => {
          setSpace(null);
          setReloads((r) => r + 1);
        }}
      />
    </ReactFlowProvider>
  );
}

function sourceSig(src: SpaceNode | undefined, jobs: Record<string, Generation>) {
  if (!src) return null;
  if (src.type === "text") return src.data.text;
  if (src.type === "media") return src.data.url ?? null;
  if (src.type === "list") return JSON.stringify(listValues(src.data));
  if (src.type === "generator") {
    const j = selectedRun(src.data);
    return j ? `${j}:${jobs[j]?.status === "completed" ? "ok" : "no"}` : null;
  }
  return null;
}

function Canvas({ space, models: list, onReload }: { space: Space; models: ModelSummary[]; onReload: () => void }) {
  const { t } = useI18n();
  const s = t.spaces;
  const flow = useReactFlow();
  const models = useMemo(() => new Map(list.map((m) => [m.id, m])), [list]);
  const outputOf = useCallback((m: string) => models.get(m)?.output, [models]);

  const [nodes, setNodes, onNodesChange] = useNodesState<SpaceNode>(space.graph.nodes.map(normalizeNode));
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(space.graph.edges);
  const [title, setTitle] = useState(space.title);
  const [viewport, setViewport] = useState<SpaceGraph["viewport"]>(space.graph.viewport);
  const [details, setDetails] = useState<Record<string, ModelDetail>>({});
  const [jobs, setJobs] = useState<Record<string, Generation>>({});
  const [gone, setGone] = useState<Set<string>>(() => new Set());
  const [estimates, setEstimates] = useState<Record<string, NodeEstimate>>({});
  const [runStates, setRunStates] = useState<Record<string, RunState>>({});
  const [menu, setMenu] = useState<Menu | null>(null);
  const [picker, setPicker] = useState<"image" | "video" | null>(null);
  const [save, setSave] = useState<"saved" | "saving" | "error" | "conflict">("saved");

  // Firmas de entrada por generador: si cambian, la cotización anterior deja de valer.
  const signatures = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const out: Record<string, string> = {};
    for (const n of nodes) {
      if (n.type !== "generator") continue;
      const ins = edges
        .filter((e) => e.target === n.id)
        .map((e) => [e.targetHandle, e.sourceHandle ?? "out", sourceSig(byId.get(e.source), jobs)])
        .sort((a, b) => String(a[0]).localeCompare(String(b[0])));
      out[n.id] = JSON.stringify([n.data.model, n.data.values, n.data.count ?? 1, ins]);
    }
    return out;
  }, [nodes, edges, jobs]);

  // Lo más reciente, para callbacks estables que corren fuera del render (clics, temporizadores).
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const jobsRef = useRef(jobs);
  const goneRef = useRef(gone);
  const detailsRef = useRef(details);
  const estimatesRef = useRef(estimates);
  const runStatesRef = useRef(runStates);
  const signaturesRef = useRef(signatures);
  useLayoutEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
    jobsRef.current = jobs;
    goneRef.current = gone;
    detailsRef.current = details;
    estimatesRef.current = estimates;
    runStatesRef.current = runStates;
    signaturesRef.current = signatures;
  });

  const patchRun = useCallback((nodeId: string, patch: RunState) => {
    setRunStates((prev) => ({ ...prev, [nodeId]: { ...prev[nodeId], ...patch } }));
  }, []);

  // Esquemas de los modelos usados: dan los puertos de cada generador.
  const usedModels = [...new Set(nodes.flatMap((n) => (n.type === "generator" ? [n.data.model] : [])))].sort().join("|");
  useEffect(() => {
    for (const m of usedModels ? usedModels.split("|") : []) {
      if (detailsRef.current[m]) continue;
      loadDetail(m).then(
        (d) => {
          setDetails((prev) => ({ ...prev, [m]: d }));
          // Conexiones a campos que el modelo ya no tiene (catálogo actualizado, grafo editado a mano).
          const keys = new Set(inPorts(d).map((p) => p.key));
          const users = new Set(nodesRef.current.filter((n) => n.type === "generator" && n.data.model === m).map((n) => n.id));
          setEdges((es) => (es.some((e) => users.has(e.target) && !keys.has(e.targetHandle ?? "")) ? es.filter((e) => !users.has(e.target) || keys.has(e.targetHandle ?? "")) : es));
        },
        () => undefined,
      );
    }
  }, [usedModels, setEdges]);

  // Sondeo de las generaciones que se ven o siguen en curso (lee la BD propia, no a los proveedores).
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const known = jobsRef.current;
      const wanted = new Set<string>();
      for (const n of nodesRef.current) {
        if (n.type !== "generator") continue;
        const j = selectedRun(n.data);
        if (j) wanted.add(j);
      }
      for (const j of Object.values(known)) if (!j.terminal) wanted.add(j.id);
      const ids = [...wanted].filter((i) => !goneRef.current.has(i) && (!known[i] || !known[i].terminal));
      if (ids.length) {
        const results = await Promise.all(
          ids.map((i) =>
            studio.get(i).then(
              (g) => ({ id: i, g, lost: false }),
              (e) => ({ id: i, g: null, lost: e instanceof StudioError && e.status === 404 }),
            ),
          ),
        );
        if (!alive) return;
        const got = results.filter((r) => r.g);
        if (got.length) setJobs((prev) => ({ ...prev, ...Object.fromEntries(got.map((r) => [r.id, r.g!])) }));
        const lost = results.filter((r) => r.lost).map((r) => r.id);
        if (lost.length) setGone((prev) => new Set([...prev, ...lost]));
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  const nodeName = useCallback(
    (n: SpaceNode) => {
      if (n.type === "generator" && isAssistant(n.data.model)) return s.assistantName;
      if (n.type === "generator")
        return isTool(n.data.model)
          ? (s.toolNames[n.data.model] ?? n.data.model)
          : (s.audioNames[n.data.model] ?? modelLabel(models.get(n.data.model)?.title ?? n.data.model).name);
      if (n.type === "media") return n.data.name || s.addMedia;
      if (n.type === "list") return `${s.addList} · ${s.listKinds[n.data.kind]}`;
      return s.addText;
    },
    [models, s],
  );

  // URL vigente de la salida de un paso previo (se sube gratis a Higgsfield y se reutiliza unos días).
  const outputUrls = useRef(new Map<string, string>());
  const sourceMedia = useCallback(
    async (src: SpaceNode, handle?: string | null): Promise<{ url: string; local?: string }> => {
      if (src.type === "media") {
        if (!src.data.url) throw new InputError(s.needsMedia(nodeName(src)));
        return { url: src.data.url };
      }
      if (src.type === "generator") {
        const jobId = selectedRun(src.data);
        const job = jobId ? jobsRef.current[jobId] : undefined;
        if (!jobId || !job || job.status !== "completed" || !job.outputs[0]) throw new InputError(s.needsUpstream(nodeName(src)));
        // Una salida extra de un video (último fotograma o audio) se extrae y sube aparte en el servidor.
        const as = isDerived(handle) ? handle : undefined;
        const cacheKey = as ? `${jobId}:${as}` : jobId;
        let url = outputUrls.current.get(cacheKey);
        if (!url) {
          url = (await studio.useOutput(jobId, 0, as)).url;
          outputUrls.current.set(cacheKey, url);
        }
        return { url, local: as ? undefined : outputSrc(job.outputs[0]) };
      }
      throw new InputError(s.needsMedia(nodeName(src)));
    },
    [nodeName, s],
  );

  /** Entrada final de un generador: sus ajustes más lo que traen sus conexiones. */
  const resolve = useCallback(
    async (nodeId: string, item?: number) => {
      // Nodos y aristas de un mismo instante: lo que cambie durante las esperas no se mezcla (revisión 51).
      const ns = nodesRef.current;
      const es = edgesRef.current;
      const node = ns.find((n): n is GeneratorNode => n.id === nodeId && n.type === "generator");
      if (!node) throw new InputError("");
      const detail = await loadDetail(node.data.model);
      const ports = inPorts(detail);
      const values: Record<string, unknown> = { ...node.data.values };
      const groups = incoming(es, nodeId);
      const durations: Promise<number | null>[] = [];
      for (const port of ports) {
        const links = (groups.get(port.key) ?? [])
          .map((e) => ({ src: ns.find((n) => n.id === e.source), handle: e.sourceHandle }))
          .filter((l): l is { src: SpaceNode; handle: string | null | undefined } => !!l.src);
        const sources = links.map((l) => l.src);
        if (!sources.length) continue;
        // Mismas reglas que las corridas del servidor: un tipo que no encaja es un error (también en el prompt)
        // y un campo simple toma la primera conexión (revisiones 55 y 56).
        if (links.some((l) => outKind(l.src, outputOf, l.handle) !== port.kind)) throw new InputError(s.wrongKind(portLabel(t, detail, port.key)));
        // Un elemento de una Lista (lote): el mismo índice en todas las listas conectadas.
        const fromList = (src: SpaceNode) => {
          const values = src.type === "list" ? listValues(src.data) : [];
          if (item === undefined || item >= values.length) throw new InputError(s.listNeedsBatch);
          return values[item];
        };
        if (port.kind === "text") {
          const texts: string[] = [];
          for (const src of sources) {
            if (src.type === "generator") {
              // El texto que escribió un Assistant (su copia local; mismas reglas que el servidor).
              const jobId = selectedRun(src.data);
              const job = jobId ? jobsRef.current[jobId] : undefined;
              if (!job || job.status !== "completed" || !job.outputs[0]) throw new InputError(s.needsUpstream(nodeName(src)));
              const res = await fetch(outputSrc(job.outputs[0]));
              if (!res.ok) throw new InputError(s.needsUpstream(nodeName(src)));
              texts.push((await res.text()).trim());
            } else if (src.type === "text") texts.push(src.data.text.trim());
            else if (src.type === "list") texts.push(fromList(src).trim());
          }
          const own = typeof values[port.key] === "string" ? (values[port.key] as string).trim() : "";
          values[port.key] = [...texts.filter(Boolean), own].filter(Boolean).join("\n\n") || undefined;
          continue;
        }
        const urls: string[] = [];
        for (const { src, handle } of port.multiple ? links : links.slice(0, 1)) {
          if (src.type === "list") {
            urls.push(fromList(src));
            continue;
          }
          const { url, local } = await sourceMedia(src, handle);
          urls.push(url);
          if (port.kind === "video") durations.push(probeDuration(local ?? url, url));
        }
        values[port.key] = port.multiple ? urls.slice(0, port.max) : urls[0];
      }
      for (const f of mediaFields(detail)) {
        if (f.media !== "video" || groups.has(f.key)) continue;
        const v = values[f.key];
        for (const url of Array.isArray(v) ? (v as string[]) : typeof v === "string" ? [v] : []) durations.push(probeDuration(url));
      }
      const input = cleanInput(values);
      const missing = ports.filter((p) => p.required && input[p.key] === undefined);
      if (missing.length) throw new InputError(s.missing(missing.map((p) => portLabel(t, detail, p.key)).join(", ")));
      const hints: Record<string, number> = {};
      const secs = await Promise.all(durations);
      if (secs.length && secs.every((x) => x)) hints.input_video_seconds = secs.reduce<number>((a, x) => a + (x ?? 0), 0);
      return { model: node.data.model, input, hints };
    },
    [sourceMedia, s, t, outputOf, nodeName],
  );

  const errorText = useCallback(
    (e: unknown) => {
      const fields = fieldErrors(e);
      if (fields) return fields.map((f) => (f.path === "(root)" ? f.message : `${f.path}: ${f.message}`)).join(" · ");
      return e instanceof Error ? e.message : String(e);
    },
    [],
  );

  type Prepared =
    | { batch: false; one: { model: string; input: Record<string, unknown>; hints: Record<string, number> } }
    | { batch: true; items: { model: string; input: Record<string, unknown>; count: number; hints: Record<string, number> }[] };

  /** Petición de un nodo: una generación, o un lote si tiene Listas conectadas (una por elemento marcado). */
  const prepare = useCallback(
    async (nodeId: string): Promise<Prepared> => {
      const ns = nodesRef.current;
      const lists = edgesRef.current
        .filter((e) => e.target === nodeId)
        .map((e) => ns.find((n) => n.id === e.source))
        .filter((n): n is ListNode => n?.type === "list");
      const count = ns.find((n): n is GeneratorNode => n.id === nodeId && n.type === "generator")?.data.count ?? 1;
      if (!lists.length) {
        const one = await resolve(nodeId);
        // Variantes: un lote de una sola petición repetida `count` veces.
        return count > 1 ? { batch: true, items: [{ ...one, count }] } : { batch: false, one };
      }
      if (count > 1) throw new InputError(s.variantsWithList);
      const sizes = new Set(lists.map((l) => listValues(l.data).length));
      if (sizes.size > 1) throw new InputError(s.batchSizes);
      const size = [...sizes][0];
      if (!size) throw new InputError(s.emptyList);
      const items = [];
      for (let i = 0; i < size; i++) items.push({ ...(await resolve(nodeId, i)), count: 1 });
      return { batch: true, items };
    },
    [resolve, s],
  );

  // Clave de idempotencia por nodo y petición exacta: se conserva entre reintentos de un mismo envío.
  const idempotency = useRef(new Map<string, string>());

  /** Cotización de una petición preparada: la de la generación o el total del lote. Un lote ya empezado (con
   * clave) cuenta lo creado con el compromiso de entonces, igual que el servidor al enviarlo (revisión 71). */
  const estimateFor = useCallback(
    async (p: Prepared, nodeId?: string): Promise<Estimate> => {
      if (!p.batch) return studio.estimate(p.one.model, p.one.input, p.one.hints);
      const key = nodeId ? idempotency.current.get(`${nodeId}|${JSON.stringify(p)}`) : undefined;
      const { total } = await studio.batch(p.items, { dryRun: true, key });
      const complete = !!total?.complete;
      return {
        kind: complete ? "exact" : "approx",
        credits: null,
        usd: total?.usd ?? null,
        discount_pct: null,
        basis: s.listBatch(p.items.reduce((a, i) => a + i.count, 0)),
        missing: complete ? [] : ["price of some items"],
        description: null,
        reserve_usd: total?.reserve_usd ?? null,
      };
    },
    [s],
  );

  const quote = useCallback(
    async (nodeId: string, sig: string) => {
      try {
        const p = await prepare(nodeId);
        const value = await estimateFor(p, nodeId);
        setEstimates((prev) => ({ ...prev, [nodeId]: { key: sig, request: JSON.stringify(p), value } }));
      } catch (e) {
        setEstimates((prev) => ({ ...prev, [nodeId]: { key: sig, value: null, error: errorText(e) } }));
      }
    },
    [prepare, estimateFor, errorText],
  );

  // Cotiza el generador seleccionado cada vez que cambian sus entradas (con debounce).
  const wantedKey = JSON.stringify(nodes.filter((n) => n.type === "generator" && n.selected).map((n) => [n.id, signatures[n.id]]));
  useEffect(() => {
    const list = JSON.parse(wantedKey) as [string, string][];
    const timer = setTimeout(() => {
      for (const [nodeId, sig] of list) if (estimatesRef.current[nodeId]?.key !== sig) quote(nodeId, sig);
    }, 450);
    return () => clearTimeout(timer);
  }, [wantedKey, quote]);

  /**
   * Generar un nodo. Solo paga si el usuario ya vio el precio de ESTA petición exacta (entrada resuelta y
   * hints): si no hay cotización vigente, este clic cotiza y el siguiente genera. Un precio desconocido
   * pide además confirmarlo. Si el lienzo cambia mientras se resuelve, se aborta (revisión 51).
   */
  const runNode = useCallback(
    async (nodeId: string) => {
      if (runStatesRef.current[nodeId]?.busy) return;
      const node = nodesRef.current.find((n): n is GeneratorNode => n.id === nodeId && n.type === "generator");
      if (!node) return;
      if (node.data.runs.length >= MAX_RUNS) {
        patchRun(nodeId, { error: s.tooManyRuns(MAX_RUNS) });
        return;
      }
      const sig = signaturesRef.current[nodeId];
      patchRun(nodeId, { busy: true, error: null });
      let keyId: string | null = null;
      let batched = false;
      try {
        const p = await prepare(nodeId);
        batched = p.batch;
        const request = JSON.stringify(p);
        if (signaturesRef.current[nodeId] !== sig) throw new InputError(s.changed);
        if (p.batch && node.data.runs.length + p.items.reduce((a, i) => a + i.count, 0) > MAX_RUNS) throw new InputError(s.tooManyRuns(MAX_RUNS));
        const cached = estimatesRef.current[nodeId];
        if (!cached?.value || cached.key !== sig || cached.request !== request) {
          const value = await estimateFor(p, nodeId);
          setEstimates((prev) => ({ ...prev, [nodeId]: { key: sig, request, value } }));
          patchRun(nodeId, { busy: false, confirm: null, confirmRequest: null });
          return;
        }
        const est = cached.value;
        const direct = costAllowsDirectSubmit(est);
        const state = runStatesRef.current[nodeId];
        if (!direct && (state?.confirm !== sig || state?.confirmRequest !== request)) {
          patchRun(nodeId, { busy: false, confirm: sig, confirmRequest: request });
          return;
        }
        keyId = `${nodeId}|${request}`;
        if (!idempotency.current.has(keyId)) idempotency.current.set(keyId, crypto.randomUUID());
        const key = idempotency.current.get(keyId)!;
        // Un lote se aprueba por su total (o, si falta algún precio y se confirmó, sin tope: no hay ambas cosas).
        const made = p.batch
          ? ((
              await studio.batch(p.items, {
                dryRun: false, key, acceptUnknown: !direct,
                maxTotalUsd: direct ? (est.usd ?? null) : null,
                // La retención vista se aprueba aparte: aceptar un costo desconocido no la borra (revisión 72).
                maxTotalReserveUsd: est.reserve_usd ?? null,
              })
            ).generations ?? [])
          : [await studio.generate(p.one.model, p.one.input, key, false, est.usd ?? null, p.one.hints, est.reserve_usd ?? null, !direct)];
        idempotency.current.delete(keyId);
        setJobs((prev) => ({ ...prev, ...Object.fromEntries(made.map((g) => [g.id, g])) }));
        setNodes((ns) =>
          ns.map((n) => {
            if (n.id !== nodeId || n.type !== "generator") return n;
            const runs = [...n.data.runs, ...made.map((g) => g.id).filter((id) => !n.data.runs.includes(id))];
            return { ...n, data: { ...n.data, runs, selected: runs.length - 1 } };
          }),
        );
        patchRun(nodeId, { busy: false, confirm: null, confirmRequest: null, error: null });
      } catch (e) {
        let message = errorText(e);
        // Cambió lo que hay que aprobar (precio, retención o un precio que ya no se conoce): se recotiza la misma
        // petición con su clave y se pide un clic nuevo sobre lo nuevo, sin reenviar ni subir topes (revisión 73).
        if (e instanceof StudioError && ["cost_changed", "reserve_not_approved", "cost_unknown"].includes(e.code ?? "")) {
          const p = await prepare(nodeId).catch(() => null);
          const fresh = p ? await estimateFor(p, nodeId).catch(() => null) : null;
          setEstimates((prev) => ({ ...prev, [nodeId]: { key: sig, request: p ? JSON.stringify(p) : undefined, value: fresh } }));
          patchRun(nodeId, { confirm: null, confirmRequest: null });
          if (e.code === "reserve_not_approved" && fresh?.reserve_usd != null) message = t.cost.reserveChanged(formatUsd(fresh.reserve_usd));
          else if (fresh?.usd != null) message = t.cost.priceChanged(formatUsd(fresh.usd));
        }
        // La clave solo se descarta ante un rechazo claro de una generación suelta (4xx: no se creó nada). Un
        // fallo de red o un 5xx pudo crear el trabajo, y un lote crea uno a uno (un 4xx puede llegar con parte
        // ya creada): el reintento reutiliza la misma clave, recupera lo creado y no paga dos veces (revisión 69).
        if (keyId && e instanceof StudioError && e.status < 500 && !batched) idempotency.current.delete(keyId);
        patchRun(nodeId, { busy: false, error: message });
      }
    },
    [prepare, estimateFor, patchRun, setNodes, errorText, t, s],
  );

  const update = useCallback<SpaceCtx["update"]>(
    (nodeId, patch) => setNodes((ns) => ns.map((n) => (n.id === nodeId ? ({ ...n, data: { ...n.data, ...patch } } as SpaceNode) : n))),
    [setNodes],
  );

  const setValue = useCallback<SpaceCtx["setValue"]>(
    (nodeId, key, value) =>
      setNodes((ns) =>
        ns.map((n) => (n.id === nodeId && n.type === "generator" ? { ...n, data: { ...n.data, values: { ...n.data.values, [key]: value } } } : n)),
      ),
    [setNodes],
  );

  const changeModel = useCallback<SpaceCtx["changeModel"]>(
    (nodeId, model) => {
      loadDetail(model).then(
        (d) => {
          setDetails((prev) => ({ ...prev, [model]: d }));
          const props = d.input_schema.properties ?? {};
          setNodes((ns) =>
            ns.map((n) => {
              if (n.id !== nodeId || n.type !== "generator") return n;
              const values = defaultsFor(d.input_schema);
              for (const [k, v] of Object.entries(n.data.values)) {
                const sch = props[k];
                if (!sch || (sch.enum && !sch.enum.includes(v as string))) continue;
                values[k] = v;
              }
              return { ...n, data: { ...n.data, model, values } };
            }),
          );
          // Las conexiones a campos que el modelo nuevo no tiene (o de otro tipo) se quitan.
          const ports = inPorts(d);
          setEdges((es) =>
            es.filter((e) => {
              if (e.target !== nodeId) return true;
              const kind = outKind(nodesRef.current.find((n) => n.id === e.source), outputOf, e.sourceHandle);
              return ports.some((p) => p.key === e.targetHandle && p.kind === kind);
            }),
          );
        },
        (e) => patchRun(nodeId, { error: errorText(e) }),
      );
    },
    [setNodes, setEdges, outputOf, patchRun, errorText],
  );

  const isValidConnection = useCallback(
    (c: Connection | Edge) => {
      const ns = nodesRef.current;
      const src = ns.find((n) => n.id === c.source);
      const tgt = ns.find((n) => n.id === c.target);
      if (!src || !tgt || tgt.type !== "generator" || !c.targetHandle) return false;
      const kind = outKind(src, outputOf, c.sourceHandle);
      const detail = detailsRef.current[tgt.data.model];
      const port = detail && inPorts(detail).find((p) => p.key === c.targetHandle);
      if (!kind || !port || port.kind !== kind) return false;
      return !reaches(edgesRef.current, c.target, c.source);
    },
    [outputOf],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      const tgt = nodesRef.current.find((n) => n.id === c.target);
      if (!tgt || tgt.type !== "generator" || !c.targetHandle) return;
      const detail = detailsRef.current[tgt.data.model];
      const port = detail && inPorts(detail).find((p) => p.key === c.targetHandle);
      if (!port) return;
      setEdges((es) => {
        const same = (e: Edge) => e.target === c.target && e.targetHandle === c.targetHandle;
        if (es.some((e) => same(e) && e.source === c.source && (e.sourceHandle ?? "out") === (c.sourceHandle ?? "out"))) return es;
        // Un campo simple recibe una sola conexión: la nueva reemplaza a la anterior.
        let next = es;
        if (!port.multiple) next = es.filter((e) => !same(e));
        else if (es.filter(same).length >= port.max) return es;
        return [...next, { id: newId("e"), source: c.source, target: c.target, sourceHandle: c.sourceHandle ?? "out", targetHandle: c.targetHandle }];
      });
    },
    [setEdges],
  );

  const center = useCallback((): Menu["at"] => {
    const el = document.querySelector(".hfs-flow")?.getBoundingClientRect();
    return el ? { x: el.left + el.width / 2 - 190, y: el.top + el.height / 3 } : { x: window.innerWidth / 2, y: window.innerHeight / 3 };
  }, []);

  const openMenu = useCallback(() => {
    const at = center();
    setMenu({ at, flowAt: flow.screenToFlowPosition({ x: at.x + 190, y: at.y }), from: null });
  }, [center, flow]);

  // Soltar una conexión en un espacio vacío abre el buscador; el nodo elegido queda conectado.
  const onConnectEnd: OnConnectEnd = useCallback(
    (event, state) => {
      if (state.isValid || !state.fromNode || state.fromHandle?.type !== "source") return;
      const src = nodesRef.current.find((n) => n.id === state.fromNode!.id);
      const handle = state.fromHandle.id ?? "out";
      const kind = outKind(src, outputOf, handle);
      if (!src || !kind) return;
      const point = "changedTouches" in event ? event.changedTouches[0] : event;
      const at = { x: point.clientX, y: point.clientY };
      setMenu({ at, flowAt: flow.screenToFlowPosition(at), from: { nodeId: src.id, kind, handle } });
    },
    [flow, outputOf],
  );

  // Clic derecho en un espacio vacío: buscador de nodos en ese punto (en vez del menú del navegador).
  const onPaneContextMenu = useCallback(
    (event: React.MouseEvent | MouseEvent) => {
      event.preventDefault();
      const at = { x: event.clientX, y: event.clientY };
      setMenu({ at, flowAt: flow.screenToFlowPosition(at), from: null, exact: true });
    },
    [flow],
  );

  const addNode = useCallback(
    (choice: AddChoice, at: XY, from: Menu["from"], exact = false) => {
      const nid = newId(choice.type === "generator" ? "gen" : choice.type);
      let position = from ? { x: at.x + 20, y: at.y - 80 } : exact ? at : { x: at.x - 140, y: at.y - 60 };
      // Sin conexión de origen ni punto elegido: a la derecha de lo que ocupe ese sitio, para no tapar otro nodo.
      for (let i = 0; !from && !exact && i < 30; i++) {
        const p = position;
        if (!nodesRef.current.some((n) => Math.abs(n.position.x - p.x) < 300 && Math.abs(n.position.y - p.y) < 200)) break;
        position = { x: p.x + 380, y: p.y };
      }
      let node: SpaceNode;
      if (choice.type === "generator") node = { id: nid, type: "generator", position, data: { model: choice.model, values: {}, runs: [] } };
      else if (choice.type === "media") node = { id: nid, type: "media", position, data: {} };
      else if (choice.type === "list") node = { id: nid, type: "list", position, data: { kind: "text", items: [] } };
      else node = { id: nid, type: choice.type, position, data: { text: "" } };
      setNodes((ns) => [...ns.map((n) => (n.selected ? { ...n, selected: false } : n)), { ...node, selected: true }]);
      if (choice.type !== "generator") return;
      loadDetail(choice.model).then(
        (d) => {
          setDetails((prev) => ({ ...prev, [choice.model]: d }));
          const ports = inPorts(d);
          const defaults = defaultsFor(d.input_schema);
          for (const p of ports) delete defaults[p.key];
          setNodes((ns) => ns.map((n) => (n.id === nid && n.type === "generator" ? { ...n, data: { ...n.data, values: { ...defaults, ...n.data.values } } } : n)));
          // Al encadenar, el medio entra por el campo principal: el fotograma final nunca va primero.
          const port = from && ports.filter((p) => p.kind === from.kind).sort((a, b) => +/end|last/.test(a.key) - +/end|last/.test(b.key))[0];
          if (from && port)
            setEdges((es) => [...es, { id: newId("e"), source: from.nodeId, target: nid, sourceHandle: from.handle, targetHandle: port.key }]);
        },
        () => undefined,
      );
    },
    [setNodes, setEdges],
  );

  // «/» abre el buscador de nodos (salvo escribiendo en un campo).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target instanceof Element ? e.target : null;
      if (e.key !== "/" || el?.closest("input, textarea, select, [contenteditable=true]")) return;
      e.preventDefault();
      openMenu();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openMenu]);

  // --- Guardado automático (con versión: otra pestaña no se pisa) -------------------------------
  const graphJson = useMemo(() => JSON.stringify(serialize(nodes, edges, viewport)), [nodes, edges, viewport]);
  // Portada: la primera imagen terminada del lienzo. `undefined` mientras falten generaciones por cargar,
  // para no borrar la portada guardada al abrir el space; `null` la quita de verdad (revisión 51).
  const cover = useMemo<string | null | undefined>(() => {
    let pending = false;
    for (const n of nodes) {
      if (n.type !== "generator") continue;
      const j = selectedRun(n.data);
      if (!j) continue;
      const job = jobs[j];
      if (!job) {
        if (!gone.has(j)) pending = true;
        continue;
      }
      const out = job.outputs[0];
      if (job.status === "completed" && out?.kind === "image" && out.file_url) return out.file_url;
    }
    return pending ? undefined : null;
  }, [nodes, jobs, gone]);
  const latest = useRef({ graphJson, title, cover });
  useLayoutEffect(() => {
    latest.current = { graphJson, title, cover };
  });
  const lastSaved = useRef(`${JSON.stringify(serialize(space.graph.nodes, space.graph.edges, space.graph.viewport))}|${space.title}`);
  const savedCover = useRef<string | null>(space.cover);
  const rejectedCovers = useRef(new Set<string>());
  const version = useRef(space.version);
  const inflight = useRef(false);
  const conflicted = useRef(false);
  const coverChanged = useCallback(
    (c: string | null | undefined) => c !== undefined && c !== savedCover.current && !(c && rejectedCovers.current.has(c)),
    [],
  );
  /** Guarda lo pendiente. Devuelve true si al terminar el servidor tiene exactamente el lienzo actual. */
  const persist = useCallback(async function persist(): Promise<boolean> {
    if (conflicted.current) return false;
    if (inflight.current) {
      await new Promise((r) => setTimeout(r, 300));
      return persist();
    }
    const { graphJson: g, title: tt, cover: c } = latest.current;
    const snapshot = `${g}|${tt}`;
    const sendCover = coverChanged(c);
    if (snapshot === lastSaved.current && !sendCover) return true;
    inflight.current = true;
    setSave("saving");
    try {
      const res = await studio.saveSpace(space.id, {
        version: version.current,
        title: tt.trim() || s.untitled,
        graph: JSON.parse(g),
        ...(sendCover ? { cover: c } : {}),
      });
      version.current = res.version;
      lastSaved.current = snapshot;
      savedCover.current = res.cover;
      setSave("saved");
    } catch (e) {
      if (e instanceof StudioError && e.code === "version_conflict") {
        conflicted.current = true;
        setSave("conflict");
      } else if (e instanceof StudioError && e.code === "invalid_cover" && c) {
        // Una portada que la API no acepta (p. ej. la generación se borró) no bloquea el guardado.
        rejectedCovers.current.add(c);
        inflight.current = false;
        return persist();
      } else setSave("error");
      return false;
    } finally {
      inflight.current = false;
    }
    const now = latest.current;
    return `${now.graphJson}|${now.title}` === lastSaved.current || persist();
  }, [space.id, s.untitled, coverChanged]);
  useEffect(() => {
    if (`${graphJson}|${title}` === lastSaved.current && !coverChanged(cover)) return;
    const timer = setTimeout(persist, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [graphJson, title, cover, persist, coverChanged]);
  // Al salir de la página se guarda lo pendiente.
  useEffect(() => () => void persist(), [persist]);

  // --- Corridas en el servidor (fase 2) --------------------------------------------------------
  const [run, setRun] = useState<SpaceRun | null>(null);
  const [runDialog, setRunDialog] = useState<{
    mode: "downstream" | "workflow";
    node_id?: string;
    version: number;
    estimate: RunEstimate;
    /** Lienzo guardado que se cotizó: si cambia, la cotización deja de valer (revisión 55). */
    snapshot: string;
    /** Idempotency-Key del arranque: un reintento no crea otra corrida (revisión 64). */
    key: string;
  } | null>(null);
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  /** Suma al historial de cada nodo las generaciones que creó una corrida (y elige la nueva). */
  const mergeRun = useCallback(
    (r: SpaceRun) => {
      setNodes((ns) => {
        let changed = false;
        // Los pasos de un lote (`nodo#i`) aportan cada uno su generación, en el orden de la corrida.
        const byNode = new Map<string, string[]>();
        for (const step of r.order) {
          const job = r.nodes[step]?.job_id;
          if (!job) continue;
          const [nodeId] = splitStep(step);
          byNode.set(nodeId, [...(byNode.get(nodeId) ?? []), job]);
        }
        const next = ns.map((n) => {
          const fresh = (byNode.get(n.id) ?? []).filter((j) => n.type === "generator" && !n.data.runs.includes(j));
          if (n.type !== "generator" || !fresh.length) return n;
          changed = true;
          const runs = [...n.data.runs, ...fresh].slice(0, MAX_RUNS);
          return { ...n, data: { ...n.data, runs, selected: runs.length - 1 } };
        });
        return changed ? next : ns;
      });
    },
    [setNodes],
  );

  // Al abrir: las corridas recientes aportan sus generaciones; la activa se sigue mostrando.
  useEffect(() => {
    studio.runs(space.id, 10).then(
      (r) => {
        for (const x of [...r.runs].reverse()) mergeRun(x);
        const active = r.runs.find((x) => RUN_ACTIVE.includes(x.status));
        if (active) setRun(active);
      },
      () => undefined,
    );
  }, [space.id, mergeRun]);

  const activeRunId = run && RUN_ACTIVE.includes(run.status) ? run.id : null;
  useEffect(() => {
    if (!activeRunId) return;
    let alive = true;
    const timer = setInterval(() => {
      studio.run(space.id, activeRunId).then(
        (r) => {
          if (!alive) return;
          setRun(r);
          mergeRun(r);
        },
        () => undefined,
      );
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [activeRunId, space.id, mergeRun]);

  const openRun = useCallback(
    async (mode: "downstream" | "workflow", nodeId?: string) => {
      setRunError(null);
      setRunBusy(true);
      try {
        // La corrida usa el grafo guardado: primero se guarda lo pendiente.
        if (!(await persist())) throw new Error(s.saveFirst);
        const snapshot = lastSaved.current;
        const body = { mode, ...(nodeId ? { node_id: nodeId } : {}), version: version.current };
        const estimate = await studio.estimateRun(space.id, body);
        if (`${latest.current.graphJson}|${latest.current.title}` !== snapshot) throw new Error(s.changed);
        setRunDialog({ ...body, estimate, snapshot, key: crypto.randomUUID() });
      } catch (e) {
        setRunError(errorText(e));
      } finally {
        setRunBusy(false);
      }
    },
    [persist, space.id, errorText, s],
  );

  const startRun = useCallback(
    async (budget: number) => {
      if (!runDialog) return;
      setRunBusy(true);
      setRunError(null);
      try {
        // Se arranca solo el lienzo que se cotizó: si cambió desde entonces, hay que volver a cotizar.
        if (`${latest.current.graphJson}|${latest.current.title}` !== runDialog.snapshot || lastSaved.current !== runDialog.snapshot) {
          setRunDialog(null);
          throw new Error(s.changed);
        }
        const { mode, node_id, version: v } = runDialog;
        const r = await studio.startRun(space.id, { mode, ...(node_id ? { node_id } : {}), version: v, max_total_usd: budget }, runDialog.key);
        setRun(r);
        setRunDialog(null);
      } catch (e) {
        setRunError(errorText(e));
      } finally {
        setRunBusy(false);
      }
    },
    [runDialog, space.id, errorText, s],
  );

  const runAction = useCallback(
    async (action: () => Promise<SpaceRun>) => {
      setRunBusy(true);
      setRunError(null);
      try {
        const r = await action();
        setRun(r);
        mergeRun(r);
      } catch (e) {
        setRunError(errorText(e));
        // Un 422 puede traer una cotización nueva ya publicada en la pausa: la barra la muestra al momento.
        if (run) studio.run(space.id, run.id).then(setRun, () => undefined);
      } finally {
        setRunBusy(false);
      }
    },
    [mergeRun, errorText, run, space.id],
  );

  // --- Publicar como flujo (fase 3c) ----------------------------------------------------------
  const [published, setPublished] = useState<Flow | null>(space.flow ?? null);
  const [publishing, setPublishing] = useState(false);
  const [publishBusy, setPublishBusy] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);
  const saveFlow = useCallback(
    async (next: Flow | null) => {
      setPublishBusy(true);
      setPublishError(null);
      try {
        // El flujo apunta a nodos del grafo guardado: primero se guarda lo pendiente.
        if (!(await persist())) throw new Error(s.saveFirst);
        const res = await studio.saveSpace(space.id, { version: version.current, flow: next });
        version.current = res.version;
        setPublished(res.flow ?? null);
        setPublishing(false);
      } catch (e) {
        setPublishError(errorText(e));
      } finally {
        setPublishBusy(false);
      }
    },
    [persist, space.id, errorText, s],
  );

  const runFrom = useCallback((nodeId: string) => void openRun("downstream", nodeId), [openRun]);
  const nameOf = useCallback(
    (step: string) => {
      const [id, item] = splitStep(step);
      const n = nodes.find((x) => x.id === id) ?? (space.graph.nodes.find((x) => x.id === id) as SpaceNode | undefined);
      const name = n ? nodeName(n) : id;
      return item === null ? name : s.step(name, item + 1);
    },
    [nodes, nodeName, space.graph.nodes, s],
  );
  // Estado de cada nodo en la corrida activa; en un lote manda lo más urgente de sus pasos.
  const runNodes = useMemo(() => {
    if (!run || !RUN_ACTIVE.includes(run.status)) return {};
    const rank = { failed: 0, skipped: 1, running: 2, pending: 3, canceled: 4, done: 5 } as const;
    const out: Record<string, SpaceRun["nodes"][string]> = {};
    for (const [step, state] of Object.entries(run.nodes)) {
      const [id] = splitStep(step);
      if (!out[id] || rank[state.status] < rank[out[id].status]) out[id] = state;
    }
    return out;
  }, [run]);

  const styledEdges = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    return edges.map((e) => {
      const kind = outKind(byId.get(e.source), outputOf, e.sourceHandle);
      const tgt = byId.get(e.target);
      const j = tgt?.type === "generator" ? selectedRun(tgt.data) : undefined;
      const busy = !!j && !!jobs[j] && !jobs[j].terminal;
      // Lo que sale de una Lista es un lote: línea punteada, como en Magnific Spaces.
      const batch = byId.get(e.source)?.type === "list";
      return { ...e, animated: busy, style: { stroke: kind ? KIND_COLOR[kind] : "#666", strokeWidth: 2, ...(batch ? { strokeDasharray: "6 4" } : {}) } };
    });
  }, [edges, nodes, jobs, outputOf]);

  const selectedGen = useMemo(() => {
    const sel = nodes.filter((n) => n.selected);
    return sel.length === 1 && sel[0].type === "generator" ? (sel[0] as GeneratorNode) : null;
  }, [nodes]);

  const times = useMemo(() => {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const out: Record<string, number> = {};
    for (const n of nodes) {
      if (n.type !== "generator") continue;
      const lists = edges.map((e) => (e.target === n.id ? byId.get(e.source) : undefined)).filter((x): x is ListNode => x?.type === "list");
      out[n.id] = lists.length ? Math.max(...lists.map((l) => listValues(l.data).length)) : (n.data.count ?? 1);
    }
    return out;
  }, [nodes, edges]);

  const ctx = useMemo<SpaceCtx>(
    () => ({ models, details, jobs, gone, edges, signatures, estimates, runStates, run: runNode, update, setValue, changeModel, runFrom, runNodes, runBusy, times }),
    [models, details, jobs, gone, edges, signatures, estimates, runStates, runNode, update, setValue, changeModel, runFrom, runNodes, runBusy, times],
  );

  const tools: { icon: typeof Type; label: string; onClick: () => void }[] = [
    { icon: Plus, label: `${s.add} (/)`, onClick: openMenu },
    { icon: Type, label: s.addText, onClick: () => addNode({ type: "text" }, flow.screenToFlowPosition({ x: center().x + 190, y: center().y }), null) },
    { icon: Upload, label: s.addMedia, onClick: () => addNode({ type: "media" }, flow.screenToFlowPosition({ x: center().x + 190, y: center().y }), null) },
    { icon: ImageIcon, label: s.addImage, onClick: () => setPicker("image") },
    { icon: Video, label: s.addVideo, onClick: () => setPicker("video") },
    { icon: StickyNote, label: s.addNote, onClick: () => addNode({ type: "note" }, flow.screenToFlowPosition({ x: center().x + 190, y: center().y }), null) },
    { icon: Maximize, label: s.fit, onClick: () => flow.fitView({ padding: 0.2, duration: 300 }) },
  ];

  return (
    <SpaceContext value={ctx}>
      <div className="flex h-[calc(100dvh-56px)] min-h-0 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-3">
          <Link href="/spaces" className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-fg-3 hover:text-fg">
            <ChevronLeft className="size-4" /> {s.back}
          </Link>
          <span className="text-fg-4">/</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            aria-label={s.renamed}
            placeholder={s.untitled}
            className="min-w-0 flex-1 bg-transparent text-[15px] font-semibold outline-none placeholder:text-fg-4"
          />
          <button
            type="button"
            onClick={() => setPublishing(true)}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold text-fg-2 hover:bg-surface-4 hover:text-fg"
          >
            <Share2 className="size-3.5" /> {published ? s.published : s.publish}
          </button>
          <button
            type="button"
            onClick={() => openRun("workflow")}
            disabled={runBusy || !!activeRunId || !nodes.some((n) => n.type === "generator")}
            className="flex items-center gap-1.5 rounded-lg bg-surface-4 px-3 py-1.5 text-[13px] font-semibold hover:bg-surface-5 disabled:opacity-40"
          >
            {runBusy && !runDialog ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5 fill-current" />}
            {s.runAll}
          </button>
          <span className={clsx("flex items-center gap-1.5 text-[12px]", save === "error" ? "text-danger" : "text-fg-3")}>
            {save === "saving" ? <Loader2 className="size-3.5 animate-spin" /> : save === "error" ? <CloudOff className="size-3.5" /> : save === "saved" ? <Check className="size-3.5" /> : null}
            {save === "saving" ? s.saving : save === "error" ? s.saveError : save === "saved" ? s.saved : null}
          </span>
        </header>

        <div className="flex min-h-0 flex-1">
          <div className="relative min-w-0 flex-1">
            <ReactFlow<SpaceNode, Edge>
              className="hfs-flow"
              nodes={nodes}
              edges={styledEdges}
              nodeTypes={NODE_TYPES}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onConnectEnd={onConnectEnd}
              onPaneContextMenu={onPaneContextMenu}
              isValidConnection={isValidConnection}
              defaultViewport={space.graph.viewport}
              onMoveEnd={(_, vp) => setViewport({ x: Math.round(vp.x), y: Math.round(vp.y), zoom: Math.round(vp.zoom * 1000) / 1000 })}
              colorMode="dark"
              minZoom={0.15}
              maxZoom={2}
              deleteKeyCode={["Backspace", "Delete"]}
            >
              <Background variant={BackgroundVariant.Dots} gap={22} size={1.3} color="rgba(255,255,255,0.12)" />
              <Controls position="bottom-right" showInteractive={false} />
              <MiniMap position="top-right" pannable zoomable maskColor="rgba(0,0,0,0.55)" nodeColor="#2a2d32" className="!bg-surface-2" />
            </ReactFlow>

            <div className="absolute top-1/2 left-3 z-10 flex -translate-y-1/2 flex-col gap-1 rounded-2xl border border-line bg-surface-2/90 p-1.5 backdrop-blur">
              {tools.map(({ icon: Icon, label, onClick }) => (
                <button key={label} type="button" onClick={onClick} title={label} aria-label={label} className="rounded-xl p-2 text-fg-2 transition hover:bg-glass hover:text-fg">
                  <Icon className="size-[18px]" />
                </button>
              ))}
            </div>

            {nodes.length === 0 && (
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="pointer-events-auto flex max-w-sm flex-col items-center gap-3 rounded-card border border-line bg-surface-1/90 p-6 text-center backdrop-blur">
                  <p className="text-sm text-fg-2">{s.hint}</p>
                  <div className="flex gap-2">
                    <button type="button" onClick={tools[1].onClick} className="rounded-xl bg-surface-4 px-3 py-2 text-sm font-semibold hover:bg-surface-5">
                      {s.addText}
                    </button>
                    <button type="button" onClick={() => setPicker("image")} className="rounded-xl bg-lime px-3 py-2 text-sm font-semibold text-ink">
                      {s.addImage}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {run && (
              <RunBanner
                run={run}
                name={nameOf}
                busy={runBusy}
                error={runDialog ? null : runError}
                onStop={() => runAction(() => studio.cancelRun(space.id, run.id))}
                onApprove={(body) => runAction(() => studio.approveRun(space.id, run.id, body))}
                onClose={() => setRun(null)}
              />
            )}
            {!run && !runDialog && runError && (
              <div className="absolute top-3 left-1/2 z-20 -translate-x-1/2 rounded-xl border border-danger/40 bg-surface-2 px-4 py-2 text-sm text-danger shadow-xl">
                {runError}
              </div>
            )}

            {save === "conflict" && (
              <div className="absolute top-3 left-1/2 z-20 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-warning/40 bg-surface-2 px-4 py-2 text-sm shadow-xl">
                <AlertTriangle className="size-4 text-warning" /> {s.conflict}
                <button type="button" onClick={onReload} className="rounded-lg bg-warning px-2.5 py-1 font-semibold text-ink">
                  {s.reload}
                </button>
              </div>
            )}
          </div>

          <aside className="hidden w-[340px] shrink-0 border-l border-line bg-surface-1 lg:block">
            <Inspector node={selectedGen} />
          </aside>
        </div>
      </div>

      {publishing && (
        <PublishDialog
          initial={published ?? { title: title || s.untitled, description: "", inputs: [] }}
          nodes={nodes}
          name={nodeName}
          busy={publishBusy}
          error={publishError}
          onSave={saveFlow}
          onClose={() => {
            setPublishing(false);
            setPublishError(null);
          }}
        />
      )}
      {runDialog && (
        <RunDialog
          estimate={runDialog.estimate}
          name={nameOf}
          busy={runBusy}
          error={runError}
          onStart={startRun}
          onClose={() => {
            setRunDialog(null);
            setRunError(null);
          }}
        />
      )}
      <AddMenu
        at={menu?.at ?? null}
        from={menu?.from?.kind ?? null}
        models={list}
        onPick={(choice) => menu && addNode(choice, menu.flowAt, menu.from, menu.exact)}
        onClose={() => setMenu(null)}
      />
      <ModelPicker
        open={picker !== null}
        models={list.filter((m) => m.output === picker)}
        onSelect={(m) => addNode({ type: "generator", model: m }, flow.screenToFlowPosition({ x: center().x + 190, y: center().y }), null)}
        onClose={() => setPicker(null)}
      />
    </SpaceContext>
  );
}
