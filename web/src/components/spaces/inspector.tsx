"use client";

import { ExternalLink, FastForward, Loader2, MousePointerClick, Play } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { FieldControl } from "@/components/studio/controls";
import { CostPanel } from "@/components/studio/cost-panel";
import { ElementPicker } from "@/components/studio/element-picker";
import { MediaSlot } from "@/components/studio/media-slot";
import { ModelPicker, ModelRow } from "@/components/studio/model-picker";
import { isAssistant, isAudioNode, isTool, mediaFields, settingFields, validValues, type GeneratorNode } from "@/lib/spaces";
import { costShort } from "@/lib/studio";
import { selectedRun, useSpace } from "./context";
import { portLabel } from "./nodes";
import { VoiceSelect } from "./voice-select";

/** Ajustes del generador elegido: modelo, opciones del esquema, medios sin conectar, costo y Generar. */
export function Inspector({ node }: { node: GeneratorNode | null }) {
  const { t } = useI18n();
  const s = t.spaces;
  const ctx = useSpace();
  const [picking, setPicking] = useState(false);

  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center text-sm text-fg-3">
        <MousePointerClick className="size-6" />
        {s.inspectorEmpty}
        <p className="text-[12px] text-fg-4">{s.hint}</p>
      </div>
    );
  }

  const { id, data } = node;
  const summary = ctx.models.get(data.model);
  const detail = ctx.details[data.model];
  const connected = new Set(ctx.edges.filter((e) => e.target === id).map((e) => e.targetHandle));
  const setValue = (key: string, v: unknown) => ctx.setValue(id, key, v);
  // Solo valores que cumplen el esquema llegan a los controles (un grafo editado a mano no rompe la vista).
  const values = detail ? validValues(detail, data.values) : {};
  const fields = detail ? settingFields(detail) : [];
  const main = fields.filter((f) => ["enum", "range", "toggle"].includes(f.kind));
  const advanced = fields.filter((f) => !["enum", "range", "toggle", "elements"].includes(f.kind) && f.key !== "voice_id");
  const voiceField = fields.some((f) => f.key === "voice_id");
  const loose = detail ? mediaFields(detail).filter((f) => !connected.has(f.key)) : [];
  const est = ctx.estimates[id];
  const fresh = est && est.key === ctx.signatures[id] ? est : null;
  const state = ctx.runStates[id] ?? {};
  const confirming = !!state.confirm && state.confirm === ctx.signatures[id];
  const jobId = selectedRun(data);
  const short = costShort(fresh?.value ?? null);
  const sameOutput = [...ctx.models.values()].filter((m) => m.output === summary?.output);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3">
        {isAssistant(data.model) ? (
          <div className="rounded-2xl border border-line bg-surface-3 px-4 py-3">
            <span className="block text-[13px] text-fg-3">{s.assistantGroup}</span>
            <span className="text-[16px] font-semibold">{s.assistantName}</span>
            <span className="mt-0.5 block text-[12px] text-fg-3">{s.assistantHint}</span>
          </div>
        ) : isTool(data.model) || isAudioNode(data.model) ? (
          // Herramientas y nodos de audio no cambian de modelo: su nombre traducido va fijo.
          <div className="rounded-2xl border border-line bg-surface-3 px-4 py-3">
            <span className="block text-[13px] text-fg-3">{isTool(data.model) ? s.tools : s.audioGroup}</span>
            <span className="text-[16px] font-semibold">{s.toolNames[data.model] ?? s.audioNames[data.model] ?? data.model}</span>
            <span className="mt-0.5 block text-[12px] text-fg-3">{s.toolHints[data.model] ?? s.audioHints[data.model]}</span>
          </div>
        ) : (
          <ModelRow model={summary} onClick={() => setPicking(true)} />
        )}
        {!detail ? (
          <div className="shimmer h-40 rounded-2xl" />
        ) : (
          <>
            {voiceField && <VoiceSelect value={values.voice_id as string | undefined} onChange={(v) => setValue("voice_id", v)} />}
            {main.map((f) => (
              <FieldControl key={`${data.model}/${f.key}`} field={f} value={values[f.key]} onChange={(v) => setValue(f.key, v)} />
            ))}
            {fields.some((f) => f.kind === "elements") && (
              <ElementPicker
                key={`${data.model}/elements`}
                value={values.elements as string[] | undefined}
                onChange={(v) => setValue("elements", v.length ? v : undefined)}
                onPick={(el) => {
                  const text = (values.prompt as string) ?? "";
                  if (!text.includes(el.mention))
                    setValue("prompt", text ? `${text.trimEnd()} ${el.mention}` : el.mention);
                }}
              />
            )}
            {loose.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="px-1 pt-1 text-[12px] font-semibold text-fg-3">{s.inputs}</p>
                {loose.map((f) => (
                  <MediaSlot
                    key={`${data.model}/${f.key}`}
                    label={portLabel(t, detail, f.key)}
                    hint=""
                    kind={f.media}
                    multiple={f.multiple}
                    max={f.max}
                    required={f.required}
                    value={values[f.key] as string | string[] | undefined}
                    onChange={(v) => setValue(f.key, v)}
                  />
                ))}
              </div>
            )}
            {advanced.length > 0 && (
              <details className="rounded-2xl border border-line bg-surface-2">
                <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-fg-2">
                  {s.advanced} <span className="font-normal text-fg-3">({advanced.length})</span>
                </summary>
                <div className="flex flex-col gap-2 px-2 pb-2">
                  {advanced.map((f) => (
                    <FieldControl key={`${data.model}/${f.key}`} field={f} value={values[f.key]} onChange={(v) => setValue(f.key, v)} />
                  ))}
                </div>
              </details>
            )}
            {jobId && (
              <Link href={`/history/${jobId}`} className="flex items-center gap-1.5 px-1 text-[12px] text-fg-3 hover:text-lime">
                <ExternalLink className="size-3.5" /> {s.openInHistory}
              </Link>
            )}
          </>
        )}
      </div>
      <div className="border-t border-line p-3">
        <CostPanel loading={!!detail && !fresh} estimate={fresh?.value ?? null} error={fresh?.error} needsConfirm={confirming} />
        <button
          type="button"
          onClick={() => ctx.run(id)}
          disabled={state.busy || !detail}
          className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[16px] font-semibold text-ink transition hover:brightness-105 disabled:opacity-50"
        >
          {state.busy ? <Loader2 className="size-5 animate-spin" /> : <Play className="size-4 fill-current" />}
          {confirming ? s.runAnyway : s.run}
          {!state.busy && !confirming && short && <span>{short}</span>}
        </button>
        <button
          type="button"
          onClick={() => ctx.runFrom(id)}
          disabled={ctx.runBusy || !detail || Object.keys(ctx.runNodes).length > 0}
          className="mt-2 flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-line-2 text-[14px] font-semibold text-fg-2 transition hover:border-lime/50 hover:text-fg disabled:opacity-40"
        >
          <FastForward className="size-4" /> {s.runFrom}
        </button>
        {state.error && <p className="mt-2 text-[12px] text-danger">{state.error}</p>}
      </div>
      <ModelPicker
        open={picking}
        models={sameOutput}
        selected={data.model}
        onSelect={(m) => ctx.changeModel(id, m)}
        onClose={() => setPicking(false)}
      />
    </div>
  );
}
