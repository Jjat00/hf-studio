"use client";

import clsx from "clsx";
import { useEffect } from "react";
import { X } from "lucide-react";
import { APERTURE_BLUR, type LightDirection, type LightPreview } from "./data";

function rgba(hex: string, alpha: number) {
  const n = parseInt(hex.replace("#", ""), 16);
  if (Number.isNaN(n)) return `rgba(255,255,255,${alpha})`;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

const POS: Record<Exclude<LightDirection, "back">, string> = {
  top: "50% 0%",
  front: "45% 38%",
  right: "100% 50%",
  left: "0% 50%",
  bottom: "50% 100%",
};

/** Esfera iluminada por las luces dadas: dirección, color, brillo y difusión (más difusa = halo más amplio). */
export function LightSphere({ lights, backdrop, dark, size = 72, className }: LightPreview & { size?: number; className?: string }) {
  const front = lights.filter((s) => s.direction !== "back");
  const back = lights.filter((s) => s.direction === "back");
  const gradients = front.map((s) => {
    const reach = 30 + s.diffuse * 0.55;
    return `radial-gradient(circle at ${POS[s.direction as Exclude<LightDirection, "back">]}, ${rgba(s.color, 0.25 + (s.brightness / 100) * 0.75)} 0%, transparent ${reach}%)`;
  });
  const shadows = back.flatMap((s) => [
    `0 0 ${6 + s.diffuse / 4}px ${1 + s.brightness / 40}px ${rgba(s.color, s.brightness / 100)}`,
    `inset 0 0 ${3 + s.diffuse / 12}px ${rgba(s.color, s.brightness / 110)}`,
  ]);
  return (
    <div className={clsx("flex items-center justify-center rounded-xl", className)} style={{ background: backdrop ?? "transparent" }}>
      <div
        aria-hidden
        className="rounded-full"
        style={{
          width: size,
          height: size,
          background: [...gradients, dark ? "#050505" : "radial-gradient(circle at 50% 40%, #2b2e33, #0d0e10 75%)"].join(", "),
          boxShadow: shadows.join(", ") || undefined,
        }}
      />
    </div>
  );
}

/** Tres figuras a distintas distancias: la apertura decide cuánto se desenfocan la de delante y la del fondo. */
export function ApertureBar({ value }: { value?: string }) {
  const blur = value ? (APERTURE_BLUR[value] ?? 2) : 2;
  return (
    <div aria-hidden className="relative flex h-20 items-end justify-center gap-6 overflow-hidden rounded-xl bg-gradient-to-b from-surface-4 to-surface-2 px-4 pb-3">
      <span className="size-6 rounded-full bg-sky-300/80" style={{ filter: `blur(${blur}px)` }} />
      <span className="flex flex-col items-center">
        <span className="size-5 rounded-full bg-lime" />
        <span className="mt-0.5 h-7 w-6 rounded-t-lg bg-lime/80" />
      </span>
      <span className="size-9 rounded-full bg-amber-300/70" style={{ filter: `blur(${blur * 1.4}px)` }} />
      <span className="absolute inset-x-0 bottom-1 mx-auto h-px w-3/4 bg-line-2" />
    </div>
  );
}

/** Tira de colores de una paleta (12 bloques iguales). */
export function PaletteStrip({ colors, className }: { colors: string[]; className?: string }) {
  return (
    <div aria-hidden className={clsx("flex overflow-hidden", className)}>
      {colors.map((c, i) => (
        <span key={`${c}-${i}`} className="h-full flex-1" style={{ background: c }} />
      ))}
    </div>
  );
}

/** Mosaico grande de una paleta: los primeros colores en bloques de distinto peso, como un fotograma abstracto. */
export function PaletteMosaic({ colors, className }: { colors: string[]; className?: string }) {
  const c = (i: number) => colors[i % Math.max(colors.length, 1)] ?? "#222";
  return (
    <div aria-hidden className={clsx("grid grid-cols-4 grid-rows-2 overflow-hidden", className)}>
      <span className="col-span-2 row-span-2" style={{ background: `linear-gradient(160deg, ${c(1)}, ${c(0)})` }} />
      <span style={{ background: c(4) }} />
      <span style={{ background: `linear-gradient(180deg, ${c(7)}, ${c(2)})` }} />
      <span style={{ background: c(5) }} />
      <span style={{ background: `linear-gradient(90deg, ${c(9)}, ${c(10)})` }} />
    </div>
  );
}

/** Ventana modal de la barra de dirección: escape y clic fuera cierran; a pantalla casi completa en móvil. */
export function CinemaModal({
  title,
  onClose,
  closeLabel,
  tabs,
  footer,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  closeLabel: string;
  tabs?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", esc);
      document.body.style.overflow = prev;
    };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={clsx(
          "flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-panel border border-line bg-surface-2 shadow-2xl sm:max-h-[86vh] sm:rounded-panel",
          wide ? "sm:max-w-4xl" : "sm:max-w-2xl",
        )}
      >
        <div className="flex items-center gap-3 border-b border-line px-5 py-3.5">
          <p className="flex-1 text-[17px] font-semibold">{title}</p>
          <button type="button" onClick={onClose} aria-label={closeLabel} className="rounded-lg p-1 text-fg-3 hover:bg-glass hover:text-fg">
            <X className="size-5" />
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
          {tabs && (
            <nav className="hide-scrollbar flex shrink-0 gap-1 overflow-x-auto border-b border-line p-2 sm:w-44 sm:flex-col sm:border-r sm:border-b-0">
              {tabs}
            </nav>
          )}
          <div className="thin-scrollbar min-h-0 min-w-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</div>
        </div>
        {footer && <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ModalTab({ active, onClick, icon, label, value }: { active: boolean; onClick: () => void; icon?: React.ReactNode; label: string; value?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors",
        active ? "bg-surface-5 text-fg" : "text-fg-3 hover:bg-glass hover:text-fg-2",
      )}
    >
      {icon}
      <span className="min-w-0">
        <span className="block text-[14px] font-semibold">{label}</span>
        {value && <span className={clsx("block truncate text-[12px]", active ? "text-lime" : "text-fg-3")}>{value}</span>}
      </span>
    </button>
  );
}

export function GhostButton({ onClick, children, className, disabled }: { onClick: () => void; children: React.ReactNode; className?: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={clsx("flex h-9 items-center gap-1.5 rounded-xl border border-line bg-surface-3 px-3 text-[13px] font-semibold text-fg-2 transition-colors hover:bg-surface-4 hover:text-fg disabled:opacity-40", className)}
    >
      {children}
    </button>
  );
}

export function PrimaryButton({ onClick, children, disabled }: { onClick: () => void; children: React.ReactNode; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-4 text-[13px] font-semibold text-ink transition-[filter] hover:brightness-105 disabled:opacity-40"
    >
      {children}
    </button>
  );
}
