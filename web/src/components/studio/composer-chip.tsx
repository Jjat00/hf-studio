"use client";

import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * Chip del compositor de abajo (como la barra de Higgsfield en Imagen): muestra un ajuste y su valor, y al pulsarlo abre
 * una ventana encima con el control completo. Se cierra con Escape o con un clic fuera.
 */
export function ComposerChip({
  icon,
  label,
  value,
  children,
  wide,
  active,
}: {
  icon?: React.ReactNode;
  label?: string;
  value: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
  active?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
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
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        title={label}
        className={clsx(
          "flex h-8 max-w-56 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-semibold whitespace-nowrap transition-colors",
          open || active ? "bg-surface-5 text-fg" : "bg-surface-4 text-fg-2 hover:text-fg",
        )}
      >
        {icon}
        <span className="truncate">{value}</span>
        <ChevronDown className={clsx("size-3.5 shrink-0 text-fg-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div
          className={clsx(
            "thin-scrollbar absolute bottom-full left-0 z-30 mb-2 max-h-[60vh] overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-2 shadow-2xl",
            wide ? "w-[min(560px,calc(100vw-2rem))]" : "w-[min(340px,calc(100vw-2rem))]",
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
