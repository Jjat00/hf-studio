"use client";

import clsx from "clsx";
import { AlertTriangle, Info, Loader2, Sparkles } from "lucide-react";
import { formatUsd, type Estimate } from "@/lib/studio";

/** Se puede generar sin confirmación extra solo si hay un precio calculado. */
export function costAllowsDirectSubmit(e: Estimate | null) {
  return !!e && (e.kind === "exact" || (e.kind === "approx" && e.missing.length === 0));
}

/** Costo siempre visible encima de Generate: exacto, aproximado, pendiente o no disponible. */
export function CostPanel({
  loading,
  estimate,
  error,
  needsConfirm,
}: {
  loading: boolean;
  estimate: Estimate | null;
  error?: string;
  needsConfirm: boolean;
}) {
  let value: React.ReactNode;
  let detail: string | null = null;
  let warn = false;

  if (loading) {
    value = (
      <span className="flex items-center gap-2 text-fg-2">
        <Loader2 className="size-4 animate-spin" /> Calculating…
      </span>
    );
  } else if (!estimate) {
    value = <span className="text-warning">Cost unavailable</span>;
    detail = error ?? "Fix the highlighted fields to see the price";
    warn = true;
  } else if (estimate.kind === "exact") {
    value = (
      <span className="flex items-center gap-2">
        <Sparkles className="size-4 fill-lime text-lime" />
        {+estimate.credits!.toFixed(3)} credits
        <span className="font-normal text-fg-3">· {formatUsd(estimate.usd!)}</span>
        {estimate.discount_pct ? (
          <span className="rounded-md bg-pink px-1.5 py-0.5 text-[11px] font-bold text-white">−{+estimate.discount_pct}%</span>
        ) : null}
      </span>
    );
    detail = estimate.basis;
  } else if (estimate.kind === "approx") {
    value = (
      <span>
        ~{formatUsd(estimate.usd!)}
        {estimate.missing.length > 0 && <span className="font-normal text-warning"> + {estimate.missing.join(", ")}</span>}
      </span>
    );
    detail = estimate.basis;
    warn = estimate.missing.length > 0;
  } else if (estimate.kind === "formula") {
    value = <span className="text-warning">Depends on {estimate.missing.join(", ") || "usage"}</span>;
    detail = estimate.missing.includes("input video duration") ? `Upload the video to see the price · ${estimate.basis}` : estimate.basis;
    warn = true;
  } else {
    value = <span className="text-warning">Price after upload</span>;
    detail = estimate.basis;
    warn = true;
  }

  return (
    <div
      className={clsx(
        "mb-2 rounded-xl border px-3.5 py-2.5",
        needsConfirm ? "border-warning/50 bg-warning/5" : "border-line bg-surface-2",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] text-fg-3">Estimated cost</span>
        {estimate?.description && (
          <span title={estimate.description} className="cursor-help text-fg-3 hover:text-fg-2">
            <Info className="size-4" />
          </span>
        )}
      </div>
      <div className="mt-0.5 text-[16px] font-semibold">{value}</div>
      {detail && <p className="mt-0.5 line-clamp-2 text-xs text-fg-3">{detail}</p>}
      {needsConfirm && warn !== undefined && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-warning">
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          The exact price can&apos;t be shown yet. Press again to generate anyway.
        </p>
      )}
    </div>
  );
}
