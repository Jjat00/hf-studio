"use client";

import clsx from "clsx";
import { AlertTriangle, Info, Loader2 } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import { costBasis, costMissing } from "@/lib/i18n/cost";
import { approxUsd, formatUsd, type Estimate } from "@/lib/studio";

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
  const { t, locale } = useI18n();
  const basis = estimate ? costBasis(estimate.basis, locale) : "";
  const missing = estimate ? costMissing(estimate.missing, locale) : "";
  let value: React.ReactNode;
  let detail: string | null = null;
  let warn = false;

  if (loading) {
    value = (
      <span className="flex items-center gap-2 text-fg-2">
        <Loader2 className="size-4 animate-spin" /> {t.cost.calculating}
      </span>
    );
  } else if (!estimate) {
    value = <span className="text-warning">{t.cost.unavailable}</span>;
    detail = error ?? t.cost.fixFields;
    warn = true;
  } else if (estimate.kind === "exact") {
    // Siempre en USD: los créditos de Higgsfield no dicen cuánto cuesta.
    value = (
      <span className="flex items-center gap-2">
        {formatUsd(estimate.usd!)} <span className="text-sm font-normal text-fg-3">USD</span>
        {estimate.discount_pct ? (
          <span className="rounded-md bg-pink px-1.5 py-0.5 text-[11px] font-bold text-white">−{+estimate.discount_pct}%</span>
        ) : null}
      </span>
    );
    detail = basis;
  } else if (estimate.kind === "approx") {
    value = (
      <span>
        {approxUsd(estimate.usd!)}
        {estimate.missing.length > 0 && <span className="font-normal text-warning"> + {missing}</span>}
      </span>
    );
    detail = basis;
    warn = estimate.missing.length > 0;
  } else if (estimate.kind === "formula") {
    value = <span className="text-warning">{t.cost.dependsOn(missing || t.cost.usage)}</span>;
    detail = estimate.missing.includes("input video duration") ? t.cost.uploadToSee(basis) : basis;
    warn = true;
  } else {
    value = <span className="text-warning">{t.cost.afterUpload}</span>;
    detail = basis;
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
        <span className="text-[13px] text-fg-3">{t.cost.estimated}</span>
        {estimate?.description && (
          <span title={t.empty.externalNote ? `${t.empty.externalNote}: ${estimate.description}` : estimate.description} className="cursor-help text-fg-3 hover:text-fg-2">
            <Info className="size-4" />
          </span>
        )}
      </div>
      <div className="mt-0.5 text-[16px] font-semibold">{value}</div>
      {detail && <p className="mt-0.5 line-clamp-2 text-xs text-fg-3">{detail}</p>}
      {!loading && estimate?.options && estimate.options.length > 0 && <ProviderComparison estimate={estimate} />}
      {needsConfirm && warn !== undefined && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-warning">
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          {t.cost.cantShowExact}
        </p>
      )}
    </div>
  );
}

/** Proveedor elegido, ahorro frente a Higgsfield y la comparación con los demás (y por qué se excluyen). */
function ProviderComparison({ estimate }: { estimate: Estimate }) {
  const { t, locale } = useI18n();
  const options = estimate.options ?? [];
  const excluded = estimate.excluded ?? [];
  const best = options[0];
  const savings = estimate.savings_vs_higgsfield;
  const total = options.length + excluded.length;
  return (
    <div className="mt-1.5 text-xs">
      {best.reserve_usd != null && <p className="text-warning">{t.cost.reserve(formatUsd(best.reserve_usd))}</p>}
      {best.notes.length > 0 && <p className="text-fg-3">{best.notes.join(" · ")}</p>}
      <p className="text-fg-2">
        <span className="font-semibold text-fg">{t.cost.via(best.title)}</span>
        {savings && savings.usd > 0 && <span className="text-lime"> · {t.cost.saves(formatUsd(savings.usd), savings.pct)}</span>}
      </p>
      {total > 1 && (
        <details className="mt-1">
          <summary className="cursor-pointer text-fg-3 hover:text-fg-2">{t.cost.compare(total)}</summary>
          <ul className="mt-1 space-y-0.5">
            {options.map((o, i) => (
              <li
                key={`${o.provider}:${o.model}`}
                title={[o.model, ...o.notes].join("\n")}
                className={clsx("flex justify-between gap-3", i === 0 ? "text-fg" : "text-fg-2")}
              >
                <span>
                  {o.title}
                  {!o.official && <span className="text-fg-3"> · {t.cost.unofficial}</span>}
                </span>
                <span className="tabular-nums">{o.usd != null ? formatUsd(o.usd) : t.cost.notAvailable}</span>
              </li>
            ))}
            {excluded.map((x) => (
              <li key={`${x.provider}:${x.model ?? ""}`} className="flex justify-between gap-3 text-fg-3">
                <span className="truncate" title={x.reason}>
                  {x.title} · {costBasis(x.reason, locale)}
                </span>
                <span className="tabular-nums">{x.usd != null ? formatUsd(x.usd) : ""}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
