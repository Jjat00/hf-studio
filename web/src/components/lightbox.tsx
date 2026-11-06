"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "@/components/i18n-provider";

export type Viewable = { src: string; kind: "image" | "video" };

/** Imágenes o videos a pantalla completa, sobre todo lo demás. Con varios, flechas (y ← →) pasan de uno a otro.
 * Se cierra con Esc, con la X o tocando el fondo. */
export function Lightbox({ items, start, onClose }: { items: Viewable[]; start: number; onClose: () => void }) {
  const { t } = useI18n();
  // Se sigue la salida abierta, no su posición: el sondeo puede añadir intentos a la galería con el visor abierto.
  const [current, setCurrent] = useState(items[start]?.src);
  const found = items.findIndex((v) => v.src === current);
  // Si la que estaba abierta desaparece (borrada), queda la de origen o la última que haya.
  const i = found >= 0 ? found : Math.max(Math.min(start, items.length - 1), 0);
  const many = items.length > 1;
  const go = (step: number) => setCurrent(items[(i + step + items.length) % items.length].src);
  const { src, kind } = items[i] ?? { src: "", kind: "image" };
  const box = useRef<HTMLDivElement>(null);
  // El foco pasa al visor: sus teclas no llegan al nodo (React Flow movería el nodo con las flechas) y vuelve al cerrar.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    box.current?.focus();
    return () => before?.focus?.();
  }, []);
  const onKey = (e: React.KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === "Escape") onClose();
    else if (many && (e.key === "ArrowRight" || e.key === "ArrowLeft")) go(e.key === "ArrowRight" ? 1 : -1);
    else return;
    e.preventDefault();
  };
  const arrow = "absolute top-1/2 -translate-y-1/2 rounded-full bg-surface-2/90 p-2 text-fg-2 hover:text-fg";
  return createPortal(
    <div
      ref={box}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      // Los eventos de un portal suben por el árbol de React: sin cortar aquí, el clic seleccionaría el nodo.
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
      onDoubleClick={(e) => e.stopPropagation()}
      onKeyDown={onKey}
      className="nokey fixed inset-0 z-[100] flex items-center justify-center bg-black/90 p-4 outline-none backdrop-blur-sm sm:p-8">
      <div className="absolute top-3 right-3 flex items-center gap-2">
        {many && (
          <span className="rounded-lg bg-surface-2/90 px-2.5 py-1.5 font-mono text-sm text-fg-2">
            {i + 1}/{items.length}
          </span>
        )}
        <a href={src} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="flex items-center gap-1.5 rounded-lg bg-surface-2/90 px-3 py-1.5 text-sm text-fg-2 hover:text-fg">
          <ExternalLink className="size-4" /> {t.spaces.openOriginal}
        </a>
        <button type="button" aria-label={t.spaces.closeView} onClick={onClose} className="rounded-lg bg-surface-2/90 p-1.5 text-fg-2 hover:text-fg">
          <X className="size-5" />
        </button>
      </div>
      {kind === "video" ? (
        <video key={src} src={src} onClick={(e) => e.stopPropagation()} className="max-h-full max-w-full rounded-lg" controls autoPlay loop playsInline />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" onClick={(e) => e.stopPropagation()} className="max-h-full max-w-full rounded-lg object-contain" />
      )}
      {many && (
        <>
          <button type="button" aria-label={t.spaces.previous} title={t.spaces.previous} onClick={(e) => (e.stopPropagation(), go(-1))} className={clsx(arrow, "left-3")}>
            <ChevronLeft className="size-6" />
          </button>
          <button type="button" aria-label={t.spaces.next} title={t.spaces.next} onClick={(e) => (e.stopPropagation(), go(1))} className={clsx(arrow, "right-3")}>
            <ChevronRight className="size-6" />
          </button>
        </>
      )}
    </div>,
    document.body,
  );
}
