"use client";

import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Loader2, Square, X } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { RUN_ACTIVE, type RunEstimate, type SpaceRun } from "@/lib/spaces";
import { formatUsd } from "@/lib/studio";

/** Cotización previa de una corrida: precio de cada paso, total y el tope que aprueba el usuario. */
export function RunDialog({
  estimate,
  name,
  busy,
  error,
  onStart,
  onClose,
}: {
  estimate: RunEstimate;
  name: (nodeId: string) => string;
  busy: boolean;
  error: string | null;
  onStart: (budget: number) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const s = t.spaces;
  const [budget, setBudget] = useState(() => (Math.ceil(estimate.total_usd * 100) / 100).toFixed(2));
  const value = Number(budget);
  const valid = budget.trim() !== "" && Number.isFinite(value) && value >= 0;
  const low = valid && value + 1e-9 < estimate.total_usd;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-panel border border-line bg-surface-1" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <p className="font-semibold">{s.runTitle}</p>
          <button type="button" aria-label={s.close} onClick={onClose} className="text-fg-3 hover:text-fg">
            <X className="size-5" />
          </button>
        </div>
        <div className="thin-scrollbar flex flex-col gap-3 overflow-y-auto p-5">
          <p className="text-sm text-fg-2">{s.runIntro}</p>
          <ol className="flex flex-col divide-y divide-line rounded-2xl border border-line bg-surface-2">
            {estimate.steps.map((step, i) => (
              <li key={step.node_id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <span className="min-w-0 truncate">
                  <span className="mr-2 font-mono text-fg-3">{i + 1}</span>
                  {name(step.node_id)}
                </span>
                <span
                  className={clsx(
                    "shrink-0 text-right",
                    step.status === "ok" ? "font-semibold" : step.status === "error" ? "text-danger" : "text-warning",
                  )}
                  title={step.error}
                >
                  {step.status === "ok" && step.usd != null
                    ? formatUsd(step.usd)
                    : step.status === "later"
                      ? s.stepLater
                      : step.status === "unknown"
                        ? s.stepUnknown
                        : s.stepError}
                </span>
              </li>
            ))}
          </ol>
          <div className="flex items-center justify-between px-1 text-sm">
            <span className="text-fg-2">{s.totalQuoted}</span>
            <span className="text-lg font-semibold">{formatUsd(estimate.total_usd)}</span>
          </div>
          {estimate.reserve_usd > 0 && <p className="px-1 text-[12px] text-fg-3">{s.holdNote(formatUsd(estimate.reserve_usd))}</p>}
          <label className="flex flex-col gap-1.5 rounded-2xl border border-line bg-surface-2 p-3.5">
            <span className="text-[13px] text-fg-3">{s.budget}</span>
            <input
              type="number"
              min={0}
              step={0.01}
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className="bg-transparent text-xl font-semibold outline-none"
            />
          </label>
          {low && <p className="px-1 text-[12px] text-warning">{s.budgetLow}</p>}
          {error && <p className="px-1 text-sm text-danger">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-line p-4">
          <button type="button" onClick={onClose} className="rounded-xl px-4 py-2 text-sm text-fg-2 hover:text-fg">
            {s.cancel}
          </button>
          <button
            type="button"
            disabled={!valid || busy}
            onClick={() => onStart(value)}
            className="flex items-center gap-2 rounded-xl bg-lime px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            {s.start} · {valid ? formatUsd(value) : "—"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Estado de la corrida en curso (o de la última) sobre el lienzo: progreso, pausas y detener. */
export function RunBanner({
  run,
  name,
  busy,
  error,
  onStop,
  onApprove,
  onClose,
}: {
  run: SpaceRun;
  name: (nodeId: string) => string;
  busy: boolean;
  error: string | null;
  onStop: () => void;
  onApprove: (body: { max_total_usd?: number; accept_unknown?: boolean }) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const s = t.spaces;
  const active = RUN_ACTIVE.includes(run.status);
  const total = run.order.length;
  const done = run.order.filter((id) => run.nodes[id]?.status === "done").length;
  const pause = run.status === "awaiting_approval" ? run.pause : null;
  // Aprobar un respaldo nunca recorta el tope de los pasos que siguen: se aprueba el mayor de los dos.
  const approveTotal = pause ? (pause.reason === "job_approval" ? Math.max(pause.needed_total_usd ?? 0, run.max_total_usd) : (pause.needed_total_usd ?? 0)) : 0;
  const finished = { completed: s.runDone, partial: s.runPartial, failed: s.runFailed, canceled: s.runCanceled } as Record<string, string>;

  return (
    <div className="absolute top-3 left-1/2 z-20 flex w-[min(640px,calc(100%-24px))] -translate-x-1/2 flex-col gap-2 rounded-2xl border border-line-2 bg-surface-2/95 px-4 py-3 text-sm shadow-xl backdrop-blur">
      <div className="flex items-center gap-3">
        {active ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-lime" />
        ) : run.status === "completed" ? (
          <CheckCircle2 className="size-4 shrink-0 text-success" />
        ) : (
          <AlertTriangle className="size-4 shrink-0 text-warning" />
        )}
        <span className="font-semibold">{active ? s.progress(done, total) : finished[run.status]}</span>
        <span className="text-fg-3">{s.spent(formatUsd(run.committed_usd), formatUsd(run.max_total_usd))}</span>
        <span className="ml-auto flex items-center gap-2">
          {active ? (
            <button type="button" disabled={busy} onClick={onStop} className="flex items-center gap-1.5 rounded-lg bg-surface-4 px-2.5 py-1 text-[13px] hover:bg-surface-5 disabled:opacity-50">
              <Square className="size-3 fill-current" /> {s.stop}
            </button>
          ) : (
            <button type="button" aria-label={s.close} onClick={onClose} className="text-fg-3 hover:text-fg">
              <X className="size-4" />
            </button>
          )}
        </span>
      </div>
      {pause && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-warning/10 px-3 py-2 text-[13px]">
          <span className="text-warning">
            {pause.reason === "over_budget"
              ? s.pausedBudget(name(pause.node), formatUsd(pause.needed_total_usd ?? 0))
              : pause.reason === "job_approval"
                ? s.pausedFallback(name(pause.node), pause.usd != null ? formatUsd(pause.usd) : s.stepUnknown, formatUsd(pause.needed_total_usd ?? 0))
                : s.pausedUnknown(name(pause.node))}
          </span>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onApprove(
                pause.reason === "unknown_cost"
                  ? { accept_unknown: true }
                  : { max_total_usd: approveTotal, ...(pause.unknown ? { accept_unknown: true } : {}) },
              )
            }
            className="ml-auto rounded-lg bg-warning px-2.5 py-1 font-semibold text-ink disabled:opacity-50"
          >
            {pause.reason === "unknown_cost" ? s.acceptUnknown : s.approveTo(formatUsd(approveTotal))}
          </button>
        </div>
      )}
      {error && <p className="text-[12px] text-danger">{error}</p>}
    </div>
  );
}
