"use client";

import clsx from "clsx";
import { ChevronDown, Copy, FastForward, Play, Spline, Trash2 } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { KIND_COLOR, type PortKind } from "@/lib/spaces";

export type BarOutput = { handle: string; kind: PortKind; label: string };

/**
 * Barra flotante sobre el nodo seleccionado (como en Magnific): generar, correr desde aquí, conexión rápida
 * (crea el siguiente nodo ya conectado a una de sus salidas), duplicar y borrar.
 */
export function NodeBar({
  generator,
  busy,
  fromBusy,
  outputs,
  onRun,
  onRunFrom,
  onQuick,
  onDuplicate,
  onDelete,
}: {
  generator: boolean;
  busy: boolean;
  /** Hay una corrida en el servidor: no se puede arrancar otra desde aquí. */
  fromBusy: boolean;
  outputs: BarOutput[];
  onRun: () => void;
  onRunFrom: () => void;
  onQuick: (out: BarOutput) => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const { t } = useI18n();
  const s = t.spaces;
  const [open, setOpen] = useState(false);
  const btn = "nodrag flex h-8 items-center gap-1 rounded-lg px-2 text-fg-2 transition hover:bg-glass hover:text-fg disabled:opacity-40";
  return (
    <div className="relative flex items-center gap-0.5 rounded-xl border border-line-2 bg-surface-2/95 p-1 text-[12px] shadow-xl backdrop-blur">
      {generator && (
        <>
          <button type="button" title={s.run} aria-label={s.run} onClick={onRun} disabled={busy} className={btn}>
            <Play className="size-3.5 fill-current" />
          </button>
          <button type="button" title={s.runFrom} aria-label={s.runFrom} onClick={onRunFrom} disabled={fromBusy} className={btn}>
            <FastForward className="size-3.5" />
          </button>
          <span className="mx-0.5 h-5 w-px bg-line" />
        </>
      )}
      {outputs.length > 0 && (
        <button
          type="button"
          title={s.quickConnect}
          aria-label={s.quickConnect}
          onClick={() => (outputs.length === 1 ? onQuick(outputs[0]) : setOpen((o) => !o))}
          className={btn}
        >
          <Spline className="size-3.5" />
          {outputs.length > 1 && <ChevronDown className="size-3" />}
        </button>
      )}
      <button type="button" title={`${s.duplicate} (Ctrl+D)`} aria-label={s.duplicate} onClick={onDuplicate} className={btn}>
        <Copy className="size-3.5" />
      </button>
      <button type="button" title={s.remove} aria-label={s.remove} onClick={onDelete} className={clsx(btn, "hover:text-danger")}>
        <Trash2 className="size-3.5" />
      </button>
      {open && (
        <div className="absolute top-full left-0 z-10 mt-1 min-w-44 rounded-xl border border-line-2 bg-surface-2 p-1 shadow-2xl">
          <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold tracking-wide text-fg-3 uppercase">{s.quickConnect}</p>
          {outputs.map((o) => (
            <button
              key={o.handle}
              type="button"
              onClick={() => {
                setOpen(false);
                onQuick(o);
              }}
              className="nodrag flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-fg-2 hover:bg-glass hover:text-fg"
            >
              <span className="size-2.5 rounded-full" style={{ background: KIND_COLOR[o.kind] }} />
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
