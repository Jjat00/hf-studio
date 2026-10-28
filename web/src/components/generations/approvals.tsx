"use client";

import { AlertTriangle, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { formatUsd, studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";
import { ApprovalActions, currentOption } from "./generation-card";

const POLL_MS = 10000;

/**
 * Aviso global de la barra: generaciones pausadas porque el proveedor aprobado falló sin cobrar y el siguiente
 * cuesta más. Se ven desde cualquier página (no solo en su tarjeta) y el panel se abre solo cuando aparece una
 * nueva, porque mientras esperan ocupan un cupo de generación.
 */
export function Approvals() {
  const { t, locale } = useI18n();
  const [items, setItems] = useState<Generation[]>([]);
  const [open, setOpen] = useState(false);
  const seen = useRef(new Set<string>());
  const root = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const { generations } = await studio.awaitingApproval();
      setItems(generations);
      const fresh = generations.some((g) => !seen.current.has(g.id));
      for (const g of generations) seen.current.add(g.id);
      if (fresh) setOpen(true);
    } catch {
      // Sin API un momento: se reintenta en el siguiente ciclo.
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (!document.hidden) await refresh();
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [refresh]);

  // Se cierra con Escape o con un clic fuera.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  if (!items.length) return null;
  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex h-8 items-center gap-1.5 rounded-lg bg-warning/15 px-2.5 text-sm font-semibold text-warning"
      >
        <AlertTriangle className="size-4" />
        {t.approval.pending(items.length)}
      </button>
      {open && (
        <div className="absolute top-full right-0 z-50 mt-1 w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl">
          <div className="mb-1 flex items-center justify-between">
            <p className="text-sm font-semibold">{t.approval.pendingTitle}</p>
            <button type="button" aria-label={t.approval.cancel} onClick={() => setOpen(false)} className="rounded-md p-1 text-fg-3 hover:text-fg">
              <X className="size-4" />
            </button>
          </div>
          <p className="mb-2 text-xs leading-snug text-fg-3">{t.approval.pendingHint}</p>
          <div className="thin-scrollbar flex max-h-[60dvh] flex-col gap-2 overflow-y-auto">
            {items.map((g) => {
              const next = currentOption(g);
              return (
                <div key={g.id} className="rounded-xl bg-surface-4 p-2.5">
                  <p className="truncate text-[13px] font-medium">{g.model}</p>
                  <p className="text-[11px] text-fg-4">{t.approval.pendingCreated(new Date(g.created_at).toLocaleString(locale))}</p>
                  {g.error && <p className="mt-1 line-clamp-3 text-xs text-fg-3">{g.error}</p>}
                  {next?.reserve_usd != null && <p className="mt-1 text-xs text-warning">{t.cost.reserve(formatUsd(next.reserve_usd))}</p>}
                  <ApprovalActions g={g} className="mt-2" onDone={refresh} />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
