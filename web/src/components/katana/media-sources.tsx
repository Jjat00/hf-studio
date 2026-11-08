"use client";

import clsx from "clsx";
import { Check, CloudUpload, Loader2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { outputSrc, studio, type KatanaPreset } from "@/lib/studio";
import type { Generation } from "@/lib/types";

export type SourceId = "presets" | "uploads" | "influencer" | "generations" | "likes";

/** Un medio elegido: `key` lo identifica en la cuadrícula; `url` es la que se envía (vigente). */
export type Picked = { key: string; url: string; title?: string; poster?: string; preset?: KatanaPreset };

type Item = { key: string; src: string; poster?: string; title?: string; preset?: KatanaPreset; generation?: string };

export const INFLUENCER_MODEL = "higgsfield/ai-influencer";

/** Cuadro modal de Katana: cabecera con título y cerrar, contenido y pie. Cierra con Escape y al pulsar fuera. */
export function KatanaModal({
  title,
  onClose,
  children,
  footer,
  aside,
  wide = true,
}: {
  title: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  aside?: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2 backdrop-blur-sm md:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true"
        className={clsx("flex max-h-full w-full flex-col overflow-hidden rounded-3xl border border-white/10 bg-surface-2 shadow-2xl", wide ? "h-[min(860px,100%)] max-w-6xl" : "max-w-5xl")}>
        <header className="flex items-center justify-between gap-3 px-5 py-4 md:px-6">
          <h2 className="text-lg font-semibold md:text-xl">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="flex size-10 items-center justify-center rounded-full bg-surface-4 text-fg-2 hover:bg-white/10">
            <X className="size-5" />
          </button>
        </header>
        <div className="mx-3 mb-3 flex min-h-0 flex-1 overflow-hidden rounded-2xl bg-surface-3 md:mx-4">
          {aside && <nav className="hidden w-60 shrink-0 border-r border-white/5 p-3 md:block">{aside}</nav>}
          <div className="min-h-0 flex-1 overflow-y-auto p-4 md:p-5">{children}</div>
        </div>
        {footer && <footer className="flex items-center justify-end gap-2 px-4 pb-4 md:px-5">{footer}</footer>}
      </div>
    </div>
  );
}

/** Pestañas tipo píldora (la activa en blanco; Influencer IA en lima, como en Higgsfield). */
export function SourceTabs({ sources, active, onChange }: { sources: SourceId[]; active: SourceId; onChange: (s: SourceId) => void }) {
  const { t } = useI18n();
  const k = t.katana;
  const label: Record<SourceId, string> = {
    presets: k.srcPresets, uploads: k.srcUploads, influencer: k.srcInfluencer, generations: k.srcGenerations, likes: k.srcLikes,
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {sources.map((s) => (
        <button key={s} type="button" onClick={() => onChange(s)}
          className={clsx("h-10 rounded-full px-4 text-[15px] font-medium transition",
            active === s ? "bg-white text-black" : s === "influencer" ? "bg-lime/15 text-lime hover:bg-lime/25" : "text-fg-2 hover:bg-white/5")}>
          {label[s]}
        </button>
      ))}
    </div>
  );
}

function errorText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

/** Cuadrícula de medios de una fuente. En Subidas, la primera casilla sube un archivo nuevo. */
export function MediaGrid({
  source,
  kind,
  presets = [],
  selected,
  onPick,
  onError,
}: {
  source: SourceId;
  kind: "video" | "image";
  presets?: KatanaPreset[];
  selected: string[];
  onPick: (p: Picked) => void;
  onError: (msg: string) => void;
}) {
  const { t } = useI18n();
  const k = t.katana;
  // Lo cargado se guarda con su fuente: al cambiar de pestaña se ve la carga hasta que llega la nueva lista.
  const want = `${source}:${kind}`;
  const [loaded, setLoaded] = useState<{ key: string; items: Item[] } | null>(null);
  const items = loaded?.key === want ? loaded.items : null;
  const [busy, setBusy] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    const fromGenerations = (list: Generation[], only?: string) =>
      list
        .filter((g) => g.status === "completed" && g.outputs[0]?.kind === kind && (!only || g.model === only))
        .map((g) => ({ key: `gen:${g.id}`, src: outputSrc(g.outputs[0]), generation: g.id, title: g.model.split("/").pop() }));
    const load = async (): Promise<Item[]> => {
      switch (source) {
        case "presets":
          return presets.map((p) => ({ key: `preset:${p.id}`, src: p.video_url, poster: p.thumbnail_url || undefined, title: p.name, preset: p }));
        case "uploads":
          return (await studio.uploads(100)).uploads
            .filter((u) => u.content_type.startsWith(`${kind}/`))
            .map((u) => ({ key: `up:${u.id}`, src: u.url, title: u.filename ?? undefined }));
        case "influencer":
          return fromGenerations((await studio.list(100)).generations, INFLUENCER_MODEL);
        case "generations":
          return fromGenerations((await studio.list(100)).generations);
        case "likes":
          return fromGenerations((await studio.list(100, false, true)).generations);
      }
    };
    load().then(
      (list) => live && setLoaded({ key: want, items: list }),
      (e) => {
        if (!live) return;
        setLoaded({ key: want, items: [] });
        onError(errorText(e));
      },
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [want, presets]);

  async function pick(item: Item) {
    if (busy) return;
    if (!item.generation) return onPick({ key: item.key, url: item.src, title: item.title, poster: item.poster, preset: item.preset });
    setBusy(item.key);
    try {
      onPick({ key: item.key, url: (await studio.useOutput(item.generation, 0)).url, title: item.title });
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  async function upload(files: FileList) {
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        const up = await studio.upload(f);
        const item = { key: `up:${up.id}`, src: up.url, title: f.name.replace(/\.[^.]+$/, "") };
        setLoaded((l) => (l ? { ...l, items: [item, ...l.items] } : l));
        onPick({ key: item.key, url: item.src, title: item.title });
      }
    } catch (e) {
      onError(errorText(e));
    } finally {
      setUploading(false);
      if (file.current) file.current.value = "";
    }
  }

  const tile = "relative overflow-hidden rounded-2xl bg-surface-4";
  const aspect = source === "presets" ? "aspect-video" : "aspect-[3/4]";
  return (
    <div className={clsx("grid gap-3", source === "presets" ? "grid-cols-2 lg:grid-cols-3" : "grid-cols-3 lg:grid-cols-4")}>
      {source === "uploads" && (
        <>
          <button type="button" onClick={() => file.current?.click()} disabled={uploading}
            className={clsx(tile, aspect, "flex flex-col items-center justify-center gap-3 border border-dashed border-white/15 hover:bg-white/5")}>
            <span className="flex size-12 items-center justify-center rounded-full bg-surface-5">
              {uploading ? <Loader2 className="size-5 animate-spin" /> : <CloudUpload className="size-5" />}
            </span>
            <span className="text-sm font-semibold">{k.uploadMedia}</span>
          </button>
          <input ref={file} type="file" className="hidden" multiple={kind === "image"}
            accept={kind === "video" ? "video/mp4,video/quicktime,video/webm" : "image/png,image/jpeg,image/webp"}
            onChange={(e) => e.target.files?.length && upload(e.target.files)} />
        </>
      )}
      {items === null && <div className="col-span-full flex justify-center py-10 text-fg-3"><Loader2 className="size-5 animate-spin" /></div>}
      {items?.length === 0 && source !== "uploads" && <p className="col-span-full py-10 text-center text-sm text-fg-3">{k.nothingHere}</p>}
      {items?.map((item) => {
        const on = selected.includes(item.key);
        return (
          <button key={item.key} type="button" onClick={() => pick(item)} title={item.title}
            className={clsx(tile, aspect, "group text-left ring-2 transition", on ? "ring-lime" : "ring-transparent hover:ring-white/30")}>
            {kind === "video" ? (
              <video src={item.src} poster={item.poster} muted loop playsInline preload="metadata"
                onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                onMouseLeave={(e) => e.currentTarget.pause()}
                className="absolute inset-0 size-full object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.src} alt="" loading="lazy" className="absolute inset-0 size-full object-cover" />
            )}
            {source === "presets" && item.title && (
              <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-6 text-xs font-semibold">{item.title}</span>
            )}
            {(on || busy === item.key) && (
              <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-lime text-black">
                {busy === item.key ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
