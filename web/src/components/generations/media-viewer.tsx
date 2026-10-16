"use client";

import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "@/components/i18n-provider";
import { outputSrc } from "@/lib/studio";
import type { Output } from "@/lib/types";

/** Visor a pantalla completa de los resultados de una generación: Esc cierra, las flechas cambian de resultado. */
export function MediaViewer({
  outputs,
  start = 0,
  title,
  caption,
  onClose,
}: {
  outputs: Output[];
  start?: number;
  title: string;
  caption?: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [index, setIndex] = useState(start);
  const count = outputs.length;
  const out = outputs[index];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") setIndex((i) => (i + 1) % count);
      else if (e.key === "ArrowLeft") setIndex((i) => (i - 1 + count) % count);
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [count, onClose]);

  if (!out) return null;
  const src = outputSrc(out);
  const nav = "flex size-11 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20";

  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-50 flex flex-col bg-black/90 backdrop-blur-sm" onClick={onClose}>
      <div className="flex items-center justify-between gap-3 px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <span className="truncate rounded-md bg-white/10 px-2 py-0.5 font-medium text-white">{title}</span>
          {count > 1 && <span className="font-mono text-xs text-white/60">{index + 1} / {count}</span>}
        </div>
        <div className="flex items-center gap-2">
          <a href={src} download target="_blank" rel="noreferrer" title={t.generation.download} aria-label={t.generation.download} className={nav}>
            <Download className="size-5" />
          </a>
          <button type="button" onClick={onClose} title={t.generation.close} aria-label={t.generation.close} className={nav}>
            <X className="size-5" />
          </button>
        </div>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-4 md:px-20">
        {out.kind === "video" ? (
          <video
            key={src}
            src={src}
            controls
            autoPlay
            loop
            playsInline
            className="max-h-full max-w-full rounded-xl"
            onClick={(e) => e.stopPropagation()}
          />
        ) : out.kind === "audio" ? (
          <audio key={src} src={src} controls autoPlay className="w-full max-w-xl" onClick={(e) => e.stopPropagation()} />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={caption ?? title} className="max-h-full max-w-full rounded-xl object-contain" onClick={(e) => e.stopPropagation()} />
        )}
        {count > 1 && (
          <>
            <button
              type="button"
              aria-label={t.generation.previous}
              onClick={(e) => {
                e.stopPropagation();
                setIndex((i) => (i - 1 + count) % count);
              }}
              className={`${nav} absolute left-3 top-1/2 -translate-y-1/2`}
            >
              <ChevronLeft className="size-6" />
            </button>
            <button
              type="button"
              aria-label={t.generation.next}
              onClick={(e) => {
                e.stopPropagation();
                setIndex((i) => (i + 1) % count);
              }}
              className={`${nav} absolute right-3 top-1/2 -translate-y-1/2`}
            >
              <ChevronRight className="size-6" />
            </button>
          </>
        )}
      </div>
      {caption && (
        <p className="mx-auto line-clamp-3 max-w-3xl px-4 py-4 text-center text-sm text-white/70" onClick={(e) => e.stopPropagation()}>
          {caption}
        </p>
      )}
    </div>,
    document.body,
  );
}
