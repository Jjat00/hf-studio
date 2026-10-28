"use client";

import clsx from "clsx";
import { AlertTriangle, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { formatUsd, studio, type PendingApproval } from "@/lib/studio";
import { ApprovalActions, currentOption } from "./generation-card";

const POLL_MS = 10000;

/**
 * Aviso global de la barra: generaciones que esperan aprobación porque su precio, su retención o su proveedor
 * cambió fuera de lo aprobado. Se ven desde cualquier página (Spaces incluido) y el panel se abre solo cuando
 * aparece una nueva, porque mientras esperan ocupan un cupo de generación. Un paso de una corrida de Spaces no se
 * aprueba aquí: se aprueba en su Space, contra el presupuesto de la corrida.
 */
export function Approvals() {
  const { t, locale } = useI18n();
  const [items, setItems] = useState<PendingApproval[]>([]);
  const [total, setTotal] = useState(0);
  const [stale, setStale] = useState(false);
  const [open, setOpen] = useState(false);
  const seen = useRef(new Set<string>());
  const root = useRef<HTMLDivElement>(null);
  // Orden de las consultas: solo se aplica una respuesta más nueva que la última aplicada, y ninguna que haya
  // salido antes de la última acción (aprobar o cancelar), que ya cambió lo que había.
  const asked = useRef(0);
  const applied = useRef(0);
  const actedAt = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++asked.current;
    try {
      const res = await studio.approvals();
      if (id <= applied.current || id <= actedAt.current) return;
      applied.current = id;
      setItems(res.generations);
      setTotal(res.total);
      setStale(false);
      const fresh = res.generations.some((g) => !seen.current.has(g.id));
      for (const g of res.generations) seen.current.add(g.id);
      if (fresh) setOpen(true);
    } catch {
      // Sin respuesta (corte, sesión vencida): lo que se ve puede no estar al día y se dice; se reintenta.
      if (id > applied.current) setStale(true);
    }
  }, []);

  /** Tras aprobar o cancelar aquí: se quita al momento y se descarta lo que siga en vuelo de antes. */
  const resolved = useCallback(
    (jobId: string) => {
      actedAt.current = asked.current;
      setItems((prev) => prev.filter((g) => g.id !== jobId));
      setTotal((n) => Math.max(0, n - 1));
      void refresh();
    },
    [refresh],
  );

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

  return (
    <div ref={root} className="relative">
      {/* Anuncio para lectores de pantalla, sin mover el foco. */}
      <span role="status" aria-live="polite" className="sr-only">
        {total ? `${t.approval.pendingTitle}: ${t.approval.pending(total)}` : ""}
      </span>
      {total > 0 && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-haspopup="true"
          className={clsx("flex h-8 items-center gap-1.5 rounded-lg bg-warning/15 px-2.5 text-sm font-semibold text-warning", stale && "opacity-60")}
        >
          <AlertTriangle className="size-4" />
          {t.approval.pending(total)}
        </button>
      )}
      {open && total > 0 && (
        <div className="absolute top-full right-0 z-50 mt-1 w-[min(420px,calc(100vw-2rem))] rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl">
          <div className="mb-1 flex items-center justify-between">
            <p className="text-sm font-semibold">{t.approval.pendingTitle}</p>
            <button type="button" aria-label={t.approval.close} onClick={() => setOpen(false)} className="rounded-md p-1 text-fg-3 hover:text-fg">
              <X className="size-4" />
            </button>
          </div>
          <p className="mb-2 text-xs leading-snug text-fg-3">{t.approval.pendingHint}</p>
          {stale && <p className="mb-2 text-xs text-warning">{t.approval.stale}</p>}
          <div className="thin-scrollbar flex max-h-[60dvh] flex-col gap-2 overflow-y-auto">
            {items.map((g) => {
              const next = currentOption(g);
              return (
                <div key={g.id} className="rounded-xl bg-surface-4 p-2.5">
                  <p className="truncate text-[13px] font-medium">{g.model}</p>
                  <p className="text-[11px] text-fg-4">{t.approval.pendingCreated(new Date(g.created_at).toLocaleString(locale))}</p>
                  {g.error && <p className="mt-1 line-clamp-3 text-xs text-fg-3">{g.error}</p>}
                  {next?.reserve_usd != null && <p className="mt-1 text-xs text-warning">{t.cost.reserve(formatUsd(next.reserve_usd))}</p>}
                  {g.space_run ? (
                    <>
                      <p className="mt-1 text-xs text-fg-3">{t.approval.inRun(g.space_run.title)}</p>
                      <Link
                        href={`/spaces/${g.space_run.space_id}`}
                        onClick={() => setOpen(false)}
                        className="mt-2 inline-flex items-center gap-1 rounded-lg bg-lime px-3 py-1.5 text-xs font-bold text-black"
                      >
                        <ExternalLink className="size-3.5" />
                        {t.approval.openRun}
                      </Link>
                    </>
                  ) : (
                    <ApprovalActions g={g} className="mt-2" onDone={() => resolved(g.id)} />
                  )}
                </div>
              );
            })}
          </div>
          {total > items.length && <p className="mt-2 text-[11px] text-fg-4">{t.approval.showing(items.length, total)}</p>}
        </div>
      )}
    </div>
  );
}
