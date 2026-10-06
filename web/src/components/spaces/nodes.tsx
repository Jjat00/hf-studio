"use client";

import { Handle, Position, useUpdateNodeInternals, type NodeProps } from "@xyflow/react";
import clsx from "clsx";
import { AlertTriangle, ChevronLeft, ChevronRight, FileAudio, ImageIcon, Loader2, Play, StickyNote, Type, Upload, Video } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { CreationsPicker } from "@/components/studio/creations-picker";
import type { Dict } from "@/lib/i18n";
import { workflowLabel } from "@/lib/i18n/workflow";
import { humanize } from "@/lib/schema";
import { inPorts, KIND_COLOR, kindOfUrl, type GeneratorNode, type MediaNode, type NoteNode, type PortKind, type TextNode } from "@/lib/spaces";
import { costShort, modelLabel, outputSrc, studio } from "@/lib/studio";
import type { ModelDetail, Output } from "@/lib/types";
import { selectedRun, useSpace } from "./context";

const KIND_ICON = { text: Type, image: ImageIcon, video: Video, audio: FileAudio };

/** Nombre corto de un puerto: el prompt, o la etiqueta traducida del campo de medios. */
export function portLabel(t: Dict, detail: ModelDetail, key: string) {
  if (key === "prompt") return t.spaces.prompt;
  if (key === "image_url" && detail.output === "image") return t.spaces.inputImage;
  const labels = t.media.labels as Record<string, readonly [string, string] | undefined>;
  return labels[key]?.[0] ?? humanize(key, {});
}

function Dot({ kind, type, id, top }: { kind: PortKind; type: "source" | "target"; id: string; top?: number | string }) {
  return (
    <Handle
      type={type}
      id={id}
      position={type === "source" ? Position.Right : Position.Left}
      className="!size-3.5 !border-[3px] !border-surface-1"
      style={{ background: KIND_COLOR[kind], ...(top !== undefined ? { top } : {}) }}
    />
  );
}

function Title({ icon: Icon, children, color }: { icon: typeof Type; children: React.ReactNode; color?: string }) {
  return (
    <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[12px] font-medium text-fg-2">
      <Icon className="size-3.5" style={color ? { color } : undefined} />
      {children}
    </div>
  );
}

function Card({ selected, children, className }: { selected?: boolean; children: React.ReactNode; className?: string }) {
  return (
    <div
      className={clsx(
        "rounded-2xl border bg-surface-2 shadow-[0_12px_40px_-20px_rgba(0,0,0,0.8)] transition-colors",
        selected ? "border-lime/70" : "border-line-2",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Preview({ out, className }: { out: Output; className?: string }) {
  const src = outputSrc(out);
  if (out.kind === "video")
    return <video src={src} className={clsx("size-full object-contain", className)} controls muted loop playsInline preload="metadata" />;
  if (out.kind === "audio") return <audio src={src} controls className="w-full" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="" className={clsx("size-full object-contain", className)} />;
}

export function TextNodeView({ id, data, selected }: NodeProps<TextNode>) {
  const { t } = useI18n();
  const { update } = useSpace();
  return (
    <div className="w-[280px]">
      <Title icon={Type} color={KIND_COLOR.text}>
        {t.spaces.addText}
      </Title>
      <Card selected={selected} className="relative">
        <textarea
          value={data.text}
          onChange={(e) => update(id, { text: e.target.value })}
          placeholder={t.spaces.textPlaceholder}
          rows={5}
          className="nodrag nowheel thin-scrollbar w-full resize-none bg-transparent p-3.5 text-[13px] leading-relaxed outline-none placeholder:text-fg-4"
        />
        <Dot kind="text" type="source" id="out" />
      </Card>
    </div>
  );
}

export function NoteNodeView({ id, data, selected }: NodeProps<NoteNode>) {
  const { t } = useI18n();
  const { update } = useSpace();
  return (
    <div
      className={clsx(
        "w-[220px] rounded-xl border bg-[#3b3612] p-1 shadow-lg",
        selected ? "border-warning/70" : "border-warning/20",
      )}
    >
      <div className="flex items-center gap-1 px-2 pt-1 text-[11px] text-warning/70">
        <StickyNote className="size-3" /> {t.spaces.addNote}
      </div>
      <textarea
        value={data.text}
        onChange={(e) => update(id, { text: e.target.value })}
        placeholder={t.spaces.notePlaceholder}
        rows={4}
        className="nodrag nowheel w-full resize-none bg-transparent p-2 text-[13px] text-[#fdf6c3] outline-none placeholder:text-warning/40"
      />
    </div>
  );
}

export function MediaNodeView({ id, data, selected }: NodeProps<MediaNode>) {
  const { t } = useI18n();
  const s = t.spaces;
  const { update } = useSpace();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState<"image" | "video" | null>(null);
  const kind = data.kind;
  const Icon = kind ? KIND_ICON[kind] : Upload;

  async function upload(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await studio.upload(file);
      update(id, { url: res.url, kind: kindOfUrl(res.content_type) ?? undefined, name: file.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="w-[260px]">
      <Title icon={Icon} color={kind ? KIND_COLOR[kind] : undefined}>
        <span className="truncate">{data.name || s.addMedia}</span>
      </Title>
      <Card selected={selected} className="relative p-2">
        {data.url && kind ? (
          <div className="flex flex-col gap-2">
            <div className="flex aspect-square items-center justify-center overflow-hidden rounded-xl bg-surface-3">
              <Preview out={{ kind, url: data.url }} />
            </div>
            <button type="button" onClick={() => update(id, { url: undefined, kind: undefined, name: undefined })} className="nodrag text-[12px] text-fg-3 hover:text-fg">
              {s.replace}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <input ref={input} type="file" accept="image/*,video/*,audio/*" className="hidden" onChange={(e) => upload(e.target.files)} />
            <button
              type="button"
              disabled={busy}
              onClick={() => input.current?.click()}
              className="nodrag flex h-20 items-center justify-center gap-2 rounded-xl border border-dashed border-line-2 text-sm text-fg-2 hover:border-lime/50 hover:text-fg"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
              {busy ? s.uploading : s.upload}
            </button>
            <div className="grid grid-cols-2 gap-1.5">
              <button type="button" onClick={() => setPicking("image")} className="nodrag rounded-lg bg-surface-4 px-2 py-1.5 text-[12px] text-fg-2 hover:text-fg">
                {s.creationsImage}
              </button>
              <button type="button" onClick={() => setPicking("video")} className="nodrag rounded-lg bg-surface-4 px-2 py-1.5 text-[12px] text-fg-2 hover:text-fg">
                {s.creationsVideo}
              </button>
            </div>
            {error && <p className="text-[12px] text-danger">{error}</p>}
          </div>
        )}
        {kind && <Dot kind={kind} type="source" id="out" />}
      </Card>
      {picking && (
        <CreationsPicker
          kind={picking}
          onPick={(url) => update(id, { url, kind: picking, name: picking === "image" ? s.creationsImage : s.creationsVideo })}
          onClose={() => setPicking(null)}
        />
      )}
    </div>
  );
}

export function GeneratorNodeView({ id, data, selected }: NodeProps<GeneratorNode>) {
  const { t, locale } = useI18n();
  const s = t.spaces;
  const { models, details, jobs, gone, edges, estimates, signatures, runStates, run, update, setValue, runNodes } = useSpace();
  const updateInternals = useUpdateNodeInternals();
  const summary = models.get(data.model);
  const detail = details[data.model];
  const ports = detail ? inPorts(detail) : [];
  const portKey = ports.map((p) => p.key).join(",");
  // Los puertos aparecen al cargar el esquema: React Flow debe volver a medir los handles.
  useEffect(() => {
    updateInternals(id);
  }, [id, portKey, updateInternals]);

  const output = (summary?.output ?? detail?.output) as PortKind | "unknown" | undefined;
  const outKind: PortKind = output === "video" || output === "audio" ? output : "image";
  const Icon = KIND_ICON[outKind];
  const { name, workflow } = summary ? modelLabel(summary.title) : { name: data.model, workflow: "" };
  const connected = new Set(edges.filter((e) => e.target === id).map((e) => e.targetHandle));
  const hasPrompt = ports.some((p) => p.key === "prompt");

  const runs = data.runs;
  const index = Math.min(data.selected ?? runs.length - 1, runs.length - 1);
  const jobId = selectedRun(data);
  const job = jobId ? jobs[jobId] : undefined;
  const out = job?.status === "completed" ? job.outputs[0] : undefined;
  const state = runStates[id] ?? {};
  const est = estimates[id];
  const fresh = est && est.key === signatures[id] ? est.value : null;
  const short = costShort(fresh);
  const confirming = !!state.confirm && state.confirm === signatures[id];
  const working = !!job && !job.terminal;

  return (
    <div className="w-[320px]">
      <Title icon={Icon} color={KIND_COLOR[outKind]}>
        <span className="truncate">{name}</span>
        {workflow && <span className="truncate font-normal text-fg-3">· {workflowLabel(workflow, locale)}</span>}
      </Title>
      <Card selected={selected}>
        {ports.length > 0 && (
          <div className="flex flex-col pt-2">
            {ports.map((p) => (
              <div key={p.key} className="relative flex h-7 items-center gap-1.5 px-3.5 text-[12px] text-fg-3">
                <Dot kind={p.kind} type="target" id={p.key} />
                <span className={clsx(connected.has(p.key) && "text-fg-2")}>
                  {detail ? portLabel(t, detail, p.key) : p.key}
                  {p.required && !connected.has(p.key) && p.key !== "prompt" && <span className="text-pink"> *</span>}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="relative px-3 pt-2">
          <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-xl bg-surface-3">
            {out ? (
              <Preview out={out} />
            ) : working ? (
              <div className="flex flex-col items-center gap-2 text-[12px] text-fg-3">
                <Loader2 className="size-6 animate-spin text-lime" />
                {job?.status === "awaiting_approval" ? s.awaiting : s.running}
                {job && <span className="font-mono">{Math.round(job.elapsed_seconds)} s</span>}
              </div>
            ) : job ? (
              <div className="flex flex-col items-center gap-1 px-4 text-center text-[12px] text-danger">
                <AlertTriangle className="size-5" />
                {s.failed}
                {job.error && <span className="line-clamp-3 text-fg-3">{job.error}</span>}
              </div>
            ) : jobId && gone.has(jobId) ? (
              <span className="text-[12px] text-fg-4">—</span>
            ) : (
              <Icon className="size-8 text-fg-4" />
            )}
          </div>
          <Dot kind={outKind} type="source" id="out" top="50%" />
        </div>

        {runs.length > 1 && (
          <div className="flex items-center justify-center gap-2 pt-1.5 text-[12px] text-fg-3">
            <button type="button" aria-label="prev" disabled={index <= 0} onClick={() => update(id, { selected: index - 1 })} className="nodrag rounded p-0.5 hover:text-fg disabled:opacity-30">
              <ChevronLeft className="size-4" />
            </button>
            <span className="font-mono">
              {index + 1}/{runs.length}
            </span>
            <button type="button" aria-label="next" disabled={index >= runs.length - 1} onClick={() => update(id, { selected: index + 1 })} className="nodrag rounded p-0.5 hover:text-fg disabled:opacity-30">
              <ChevronRight className="size-4" />
            </button>
          </div>
        )}

        {hasPrompt && (
          <div className="px-3 pt-2">
            <textarea
              value={typeof data.values.prompt === "string" ? data.values.prompt : ""}
              onChange={(e) => setValue(id, "prompt", e.target.value || undefined)}
              placeholder={outKind === "video" ? s.promptVideo : s.promptImage}
              rows={3}
              className="nodrag nowheel thin-scrollbar w-full resize-none rounded-xl bg-surface-3 p-2.5 text-[13px] leading-relaxed outline-none placeholder:text-fg-4 focus:bg-surface-4"
            />
            {connected.has("prompt") && <p className="px-1 text-[11px] text-fg-4">{s.promptJoined}</p>}
          </div>
        )}

        <div className="p-3">
          <button
            type="button"
            onClick={() => run(id)}
            disabled={state.busy || !detail}
            className="nodrag flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-lime text-[14px] font-semibold text-ink transition hover:brightness-105 disabled:opacity-50"
          >
            {state.busy ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4 fill-current" />}
            {confirming ? s.runAnyway : s.run}
            {!state.busy && !confirming && short && <span className="opacity-80">· {short}</span>}
          </button>
          {state.error && <p className="mt-1.5 text-[12px] text-danger">{state.error}</p>}
          {runNodes[id]?.status === "pending" && <p className="mt-1.5 text-[12px] text-lime">{s.inRun}</p>}
          {runNodes[id]?.status === "skipped" && <p className="mt-1.5 text-[12px] text-warning">{s.skipped}</p>}
          {runNodes[id]?.status === "failed" && runNodes[id]?.error && <p className="mt-1.5 text-[12px] text-danger">{runNodes[id].error}</p>}
          {confirming && <p className="mt-1.5 text-[12px] text-warning">{s.unknownCost}</p>}
          {job && !job.terminal && job.status === "awaiting_approval" && !runNodes[id] && (
            <Link href={`/history/${job.id}`} className="nodrag mt-1.5 block text-[12px] text-lime hover:underline">
              {s.openInHistory}
            </Link>
          )}
        </div>
      </Card>
    </div>
  );
}
