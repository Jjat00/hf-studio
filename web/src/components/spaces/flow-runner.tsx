"use client";

import { Loader2, Play, Workflow } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { MediaSlot } from "@/components/studio/media-slot";
import { isAssistant, isAudioNode, isTool, RUN_ACTIVE, splitStep, type FlowSummary, type RunEstimate, type Space, type SpaceRun } from "@/lib/spaces";
import { fieldErrors, modelLabel, studio } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";
import { Preview } from "./nodes";
import { RunBanner, RunDialog } from "./run-panel";

/** Correr un Space publicado como flujo: sus entradas en un formulario, cotizar, aprobar el tope y ver el resultado. */
export function FlowRunner({ spaceId }: { spaceId: string }) {
  const { t } = useI18n();
  const s = t.spaces;
  const [flow, setFlow] = useState<FlowSummary | null | undefined>(undefined);
  const [space, setSpace] = useState<Space | null>(null);
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [dialog, setDialog] = useState<{ estimate: RunEstimate; inputs: Record<string, unknown>; key: string } | null>(null);
  const [run, setRun] = useState<SpaceRun | null>(null);
  const [jobs, setJobs] = useState<Record<string, Generation>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errorText = (e: unknown) => {
    const fields = fieldErrors(e);
    if (fields) return fields.map((f) => f.message).join(" · ");
    return e instanceof Error ? e.message : String(e);
  };

  useEffect(() => {
    studio.flows().then(
      (r) => setFlow(r.flows.find((f) => f.space_id === spaceId) ?? null),
      (e) => setError(errorText(e)),
    );
    studio.space(spaceId).then(setSpace, () => undefined);
    studio.models().then((r) => setModels(new Map(r.models.map((m) => [m.id, m]))), () => undefined);
  }, [spaceId]);

  const name = useCallback(
    (step: string) => {
      const [id, item] = splitStep(step);
      const node = space?.graph.nodes.find((n) => n.id === id);
      let label = id;
      if (node?.type === "generator") {
        const m = node.data.model;
        label = isAssistant(m)
          ? s.assistantName
          : isTool(m)
            ? (s.toolNames[m] ?? m)
            : isAudioNode(m)
              ? (s.audioNames[m] ?? m)
              : modelLabel(models.get(m)?.title ?? m).name;
      }
      return item === null ? label : s.step(label, item + 1);
    },
    [space, models, s],
  );

  // Seguir la corrida y traer las generaciones terminadas.
  const activeId = run && RUN_ACTIVE.includes(run.status) ? run.id : null;
  useEffect(() => {
    if (!activeId) return;
    const timer = setInterval(() => studio.run(spaceId, activeId).then(setRun, () => undefined), 2500);
    return () => clearInterval(timer);
  }, [activeId, spaceId]);
  const doneJobs = useMemo(() => (run ? run.order.map((st) => run.nodes[st]).filter((n) => n?.status === "done" && n.job_id).map((n) => n.job_id!) : []), [run]);
  useEffect(() => {
    for (const id of doneJobs) if (!jobs[id]) studio.get(id).then((g) => setJobs((prev) => ({ ...prev, [id]: g })), () => undefined);
  }, [doneJobs, jobs]);

  function inputsFromForm(f: FlowSummary) {
    const out: Record<string, unknown> = {};
    for (const i of f.inputs) {
      const v = values[i.node_id];
      if (v === undefined || v === "") continue;
      if (i.type === "list" && i.kind === "text") out[i.node_id] = String(v).split("\n").map((x) => x.trim()).filter(Boolean);
      else out[i.node_id] = v;
    }
    return out;
  }

  async function quote() {
    if (!flow) return;
    setBusy(true);
    setError(null);
    try {
      const inputs = inputsFromForm(flow);
      const estimate = await studio.estimateRun(spaceId, { mode: "workflow", version: flow.version, inputs });
      setDialog({ estimate, inputs, key: crypto.randomUUID() });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function start(budget: number) {
    if (!flow || !dialog) return;
    setBusy(true);
    setError(null);
    try {
      const r = await studio.startRun(spaceId, { mode: "workflow", version: flow.version, max_total_usd: budget, inputs: dialog.inputs }, dialog.key);
      setRun(r);
      setJobs({});
      setDialog(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function act(action: () => Promise<SpaceRun>) {
    setBusy(true);
    setError(null);
    try {
      setRun(await action());
    } catch (e) {
      setError(errorText(e));
      if (run) studio.run(spaceId, run.id).then(setRun, () => undefined);
    } finally {
      setBusy(false);
    }
  }

  if (flow === undefined) return <div className="shimmer m-8 h-64 rounded-panel" />;
  if (flow === null)
    return (
      <div className="mx-auto max-w-lg p-12 text-center text-fg-2">
        <p>{s.flowMissing}</p>
        <Link href="/presets" className="mt-3 inline-block text-sm text-lime hover:underline">
          {t.nav.presets}
        </Link>
      </div>
    );

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8">
      <div>
        <p className="flex items-center gap-1.5 text-sm text-fg-3">
          <Workflow className="size-4" /> {s.flows}
        </p>
        <h1 className="headline mt-1 text-[36px] text-lime">{flow.title}</h1>
        {flow.description && <p className="mt-1 text-fg-2">{flow.description}</p>}
        <Link href={`/spaces/${spaceId}`} className="mt-2 inline-block text-[13px] text-fg-3 hover:text-lime">
          {s.flowOpen}
        </Link>
      </div>

      <div className="flex flex-col gap-3 rounded-panel border border-line bg-surface-1 p-4">
        {flow.inputs.map((i) => {
          const set = (v: unknown) => setValues((prev) => ({ ...prev, [i.node_id]: v }));
          if (i.type === "text" || (i.type === "list" && i.kind === "text"))
            return (
              <label key={i.node_id} className="flex flex-col gap-1.5 text-[14px] font-semibold">
                {i.label}
                <textarea
                  value={(values[i.node_id] as string) ?? ""}
                  onChange={(e) => set(e.target.value)}
                  rows={i.type === "list" ? 5 : 3}
                  placeholder={i.type === "list" ? s.flowLines : ""}
                  className="resize-none rounded-xl bg-surface-3 p-3 text-[14px] font-normal outline-none placeholder:text-fg-4"
                />
              </label>
            );
          const kind = (i.kind ?? "image") as "image" | "video" | "audio";
          return (
            <MediaSlot
              key={i.node_id}
              label={i.label}
              hint={i.type === "list" ? s.listBatch(20) : ""}
              kind={kind}
              multiple={i.type === "list"}
              max={i.type === "list" ? 20 : 1}
              required={false}
              value={values[i.node_id] as string | string[] | undefined}
              onChange={set}
            />
          );
        })}
        <button
          type="button"
          onClick={quote}
          disabled={busy || (!!run && RUN_ACTIVE.includes(run.status))}
          className="flex h-12 items-center justify-center gap-2 rounded-xl bg-lime font-semibold text-ink disabled:opacity-50"
        >
          {busy && !dialog ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4 fill-current" />}
          {s.flowRun}
        </button>
        {error && !dialog && <p className="text-sm text-danger">{error}</p>}
      </div>

      {run && (
        <div className="relative min-h-[110px]">
          <RunBanner
            run={run}
            name={name}
            busy={busy}
            error={null}
            onStop={() => act(() => studio.cancelRun(spaceId, run.id))}
            onApprove={(body) => act(() => studio.approveRun(spaceId, run.id, body))}
            onClose={() => setRun(null)}
          />
        </div>
      )}

      {doneJobs.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="font-semibold">{s.flowResults}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {run!.order
              .filter((st) => run!.nodes[st]?.status === "done")
              .map((st) => {
                const g = jobs[run!.nodes[st].job_id!];
                const out = g?.outputs[0];
                return (
                  <div key={st} className="overflow-hidden rounded-2xl border border-line bg-surface-2">
                    <div className="flex aspect-video items-center justify-center bg-surface-3">{out ? <Preview out={out} /> : <Loader2 className="size-5 animate-spin text-fg-3" />}</div>
                    <p className="px-3 py-2 text-[13px] text-fg-2">{name(st)}</p>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {dialog && (
        <RunDialog estimate={dialog.estimate} name={name} busy={busy} error={error} onStart={start} onClose={() => setDialog(null)} />
      )}
    </div>
  );
}
