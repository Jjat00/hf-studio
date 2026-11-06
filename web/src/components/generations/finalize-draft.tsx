"use client";

import clsx from "clsx";
import { Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { useI18n } from "@/components/i18n-provider";
import { costShort, studio, StudioError } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/** Familia del borrador de Seedance 2.5 y su modelo final (ver `store/seedance_draft.py`). */
export const DRAFT_FAMILY = "bytedance/seedance-2.5-draft/";
export const DRAFT_FINAL = `${DRAFT_FAMILY}final`;

export function isFinishableDraft(g: Pick<Generation, "model" | "status">) {
  return g.status === "completed" && g.model.startsWith(DRAFT_FAMILY) && g.model !== DRAFT_FINAL;
}

/**
 * «Pasar a 1080p»: el mismo borrador (prompt, referencias, duración, semilla) renderizado a 1080p en la tienda que
 * lo hizo. Cotiza, muestra el precio, y solo con el OK del usuario genera con ese tope. `onStarted` recibe la nueva
 * generación; sin él, abre su detalle.
 */
export function FinalizeDraft({
  g,
  variant = "button",
  onStarted,
}: {
  g: Generation;
  variant?: "button" | "icon";
  onStarted?: (job: Generation) => void;
}) {
  const { t } = useI18n();
  const f = t.generation.draft;
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef("");
  if (!isFinishableDraft(g)) return null;

  async function finish() {
    setBusy(true);
    setError(null);
    const input = { draft_generation_id: g.id };
    try {
      const estimate = await studio.estimate(DRAFT_FINAL, input);
      const known = costAllowsDirectSubmit(estimate);
      const price = costShort(estimate) ?? t.cost.unavailable;
      if (!window.confirm(known ? f.confirm(price) : f.confirmUnknown)) return;
      key.current ||= crypto.randomUUID();
      const job = await studio.generate(
        DRAFT_FINAL,
        input,
        key.current,
        false,
        known ? estimate.usd : null,
        {},
        estimate.reserve_usd ?? null,
        !known,
      );
      if (onStarted) onStarted(job);
      else router.push(`/history/${job.id}`);
    } catch (e) {
      key.current = "";
      setError(e instanceof StudioError ? e.message : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (variant === "icon") {
    return (
      <button
        type="button"
        onClick={finish}
        disabled={busy}
        title={error ?? f.finish}
        aria-label={f.finish}
        className={clsx(
          "flex size-8 items-center justify-center rounded-lg hover:bg-glass disabled:opacity-50",
          error ? "text-danger" : "text-lime",
        )}
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={finish}
        disabled={busy}
        className="flex h-9 items-center justify-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink transition hover:brightness-105 disabled:opacity-50"
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
        {f.finish}
      </button>
      <p className="text-xs text-fg-3">{error ? <span className="text-danger">{error}</span> : f.hint}</p>
    </div>
  );
}
