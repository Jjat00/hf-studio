"use client";

import clsx from "clsx";
import { Check, EyeOff, Eye, Star } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { Masonry } from "@/components/masonry";
import { useI18n } from "@/components/i18n-provider";
import { outputOf, reuseHref, studio, modelMap } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";

const FILTERS = ["all", "favorites", "video", "image", "audio", "active", "failed"] as const;

/**
 * Biblioteca: todo lo generado (`/history`) o lo que se ocultó de ella (`hidden`, en `/history/hidden`, una página
 * sin enlaces a la que solo se llega escribiendo su dirección). En modo selección se marcan varias para ocultarlas
 * o volver a mostrarlas de una vez; solo las terminadas se pueden marcar.
 */
export function HistoryView({ hidden = false }: { hidden?: boolean }) {
  const { t } = useI18n();
  const h = t.history;
  const router = useRouter();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  // «Favoritas» se pide al servidor: aparecen aunque sean más antiguas que las últimas de la biblioteca.
  const favorites = filter === "favorites";
  const { items, loading, error, remove, setHidden, setFavorite, hasMore, loadingMore, loadMore } = useGenerations({
    hidden,
    favorite: favorites,
  });
  const sentinel = useRef<HTMLDivElement>(null);
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    studio.models().then((r) => setModels(modelMap(r.models))).catch(() => undefined);
  }, []);

  const shown = useMemo(
    () =>
      items.filter((g) => {
        const out = outputOf(g.model, models);
        if (filter === "video" || filter === "image" || filter === "audio") return out === filter;
        if (filter === "active") return !g.terminal;
        if (filter === "failed") return g.terminal && g.status !== "completed";
        if (filter === "favorites") return !!g.favorite;
        return true;
      }),
    [items, models, filter],
  );
  // Solo cuenta lo marcado que se ve (una que se borró, cambió de lista o quedó fuera del filtro no se toca).
  const chosen = useMemo(() => shown.filter((g) => picked.has(g.id) && g.terminal).map((g) => g.id), [shown, picked]);

  // Scroll infinito: al acercarse al final se amplía la ventana una página. El observador se rehace con cada página
  // para que, si el final sigue a la vista (p. ej. un filtro con pocas tarjetas), se pida otra.
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore || loading || loadingMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) loadMore();
    }, { rootMargin: "800px 0px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loading, loadingMore, loadMore, items.length]);

  const reuse = (g: Generation) => router.push(reuseHref(g.model, g.id, models));
  const toggle = (g: Generation) => {
    if (!g.terminal) {
      setNotice(h.stillActive);
      return;
    }
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(g.id)) next.delete(g.id);
      else next.add(g.id);
      return next;
    });
  };
  const exit = () => {
    setSelecting(false);
    setPicked(new Set());
    setNotice(null);
  };
  async function apply(action: "hide" | "favorite") {
    if (!chosen.length) return;
    setBusy(true);
    setNotice(null);
    try {
      const res = action === "hide" ? await setHidden(chosen, !hidden) : await setFavorite(chosen, !favorites);
      setPicked(new Set());
      if (res.skipped.length) setNotice(h.skipped(res.skipped.length));
      else setSelecting(false);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-4 py-8 pb-28 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{hidden ? h.hiddenTitle : h.title}</h1>
      <p className="mt-2 text-fg-3">{hidden ? h.hiddenSubtitle : h.subtitle}</p>
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => {
              setFilter(f);
              setPicked(new Set()); // cambiar de filtro empieza una selección nueva
            }}
            className={clsx(
              "h-10 rounded-xl px-4 text-[15px] font-medium transition-colors",
              filter === f ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg-2",
            )}
          >
            {h.filters[f]}
          </button>
        ))}
        <button
          type="button"
          onClick={() => (selecting ? exit() : setSelecting(true))}
          aria-pressed={selecting}
          className={clsx(
            "ml-auto h-10 rounded-xl px-4 text-[15px] font-medium transition-colors",
            selecting ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg",
          )}
        >
          {selecting ? h.done : h.select}
        </button>
      </div>
      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      {loading ? (
        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="shimmer aspect-video rounded-2xl" />
          ))}
        </div>
      ) : shown.length === 0 && !hasMore && !loadingMore ? (
        <p className="mt-16 text-center text-fg-3">{hidden ? h.hiddenNothing : favorites ? h.favoritesNothing : h.nothing}</p>
      ) : (
        <div className="mt-6">
          <Masonry
            items={shown}
            itemKey={(g) => g.id}
            maxColumns={4}
            minColumnWidth={280}
            gap={20}
            render={(g) => {
              const on = picked.has(g.id);
              return (
                <div className="relative">
                  {/* Mientras se selecciona, la tarjeta es inerte: ni el puntero ni Tab llegan a sus controles (abrir,
                      reproducir, borrar); solo el botón de selección. */}
                  <div inert={selecting}>
                    <GenerationCard
                      g={g}
                      layout="grid"
                      models={models}
                      onReuse={reuse}
                      onDelete={remove}
                      onFavorite={(x) => void setFavorite([x.id], !x.favorite).catch(() => undefined)}
                    />
                  </div>
                  {selecting && (
                    // Encima de la tarjeta: en modo selección un clic marca, no abre ni reproduce.
                    <button
                      type="button"
                      onClick={() => toggle(g)}
                      aria-pressed={on}
                      aria-label={g.model}
                      className={clsx(
                        "absolute inset-0 rounded-2xl transition",
                        on ? "bg-lime/10 ring-2 ring-lime" : "hover:bg-white/5",
                        !g.terminal && "cursor-not-allowed bg-black/40",
                      )}
                    >
                      <span
                        className={clsx(
                          "absolute top-3 left-3 flex size-6 items-center justify-center rounded-md border-2",
                          on ? "border-lime bg-lime text-ink" : "border-white/70 bg-black/40",
                        )}
                      >
                        {on && <Check className="size-4" />}
                      </span>
                    </button>
                  )}
                </div>
              );
            }}
          />
        </div>
      )}
      {!loading && (hasMore || loadingMore) && (
        <div ref={sentinel} className="flex h-16 items-center justify-center text-sm text-fg-3" aria-live="polite">
          {loadingMore && h.loadingMore}
        </div>
      )}
      {selecting && (
        <div className="fixed inset-x-0 bottom-4 z-30 mx-auto flex w-[min(640px,calc(100vw-2rem))] flex-wrap items-center gap-2 rounded-2xl border border-line-2 bg-surface-3 p-2.5 shadow-2xl">
          <span className="px-2 text-sm font-medium">{h.selected(chosen.length)}</span>
          <button
            type="button"
            onClick={() => setPicked(new Set(shown.filter((g) => g.terminal).map((g) => g.id)))}
            className="h-9 rounded-xl px-3 text-sm text-fg-2 hover:text-fg"
          >
            {h.selectAll}
          </button>
          {!hidden && (
            <button
              type="button"
              disabled={!chosen.length || busy}
              onClick={() => apply("favorite")}
              className="ml-auto flex h-9 items-center gap-1.5 rounded-xl bg-surface-4 px-4 text-sm font-semibold text-fg disabled:opacity-40"
            >
              <Star className="size-4" />
              {favorites ? h.unfavorite(chosen.length) : h.favorite(chosen.length)}
            </button>
          )}
          <button
            type="button"
            disabled={!chosen.length || busy}
            onClick={() => apply("hide")}
            className={clsx("flex h-9 items-center gap-1.5 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-40", hidden && "ml-auto")}
          >
            {hidden ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            {hidden ? h.unhide(chosen.length) : h.hide(chosen.length)}
          </button>
          {notice && <p className="w-full px-2 text-xs text-warning">{notice}</p>}
        </div>
      )}
    </div>
  );
}
