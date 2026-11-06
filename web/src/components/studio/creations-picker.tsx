"use client";

import { Check, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { outputSrc, studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/** Ventana para elegir creaciones propias (imagen o video) como entrada. Llama a `onPick` con la URL vigente de
 * cada una. Con `max` mayor que 1 se marcan varias y se añaden juntas, en el orden en que se marcaron. */
export function CreationsPicker({
  kind,
  onPick,
  onClose,
  max = 1,
}: {
  kind: "image" | "video";
  onPick: (url: string) => void;
  onClose: () => void;
  max?: number;
}) {
  const { t } = useI18n();
  const r = t.reuseAs;
  const [items, setItems] = useState<Generation[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const many = max > 1;

  useEffect(() => {
    studio.list(100).then(
      (res) => setItems(res.generations.filter((g) => g.status === "completed" && g.outputs[0]?.kind === kind)),
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setItems([]); // termina la carga aunque falle
      },
    );
  }, [kind]);

  function toggle(g: Generation) {
    setSelected((prev) =>
      prev.includes(g.id) ? prev.filter((id) => id !== g.id) : prev.length >= max ? prev : [...prev, g.id],
    );
  }

  async function addSelected() {
    setError(null);
    try {
      for (const id of selected) {
        setBusy(id);
        onPick((await studio.useOutput(id, 0)).url);
      }
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function pick(g: Generation) {
    setBusy(g.id);
    setError(null);
    try {
      onPick((await studio.useOutput(g.id, 0)).url);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-3xl flex-col rounded-card border border-line bg-surface-1"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <p className="font-semibold">{many ? r.pickTitleMany(max) : r.pickTitle}</p>
          <button type="button" aria-label={r.close} onClick={onClose} className="text-fg-3 hover:text-fg">
            <X className="size-5" />
          </button>
        </div>
        <div className="overflow-y-auto p-3">
          {error && <p className="mb-2 text-sm text-danger">{error}</p>}
          {items === null ? (
            <div className="shimmer h-40 rounded-xl" />
          ) : items.length === 0 ? (
            <p className="p-4 text-sm text-fg-3">{r.none}</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {items.map((g) => {
                const src = outputSrc(g.outputs[0]);
                const prompt = typeof g.input.prompt === "string" ? g.input.prompt : "";
                return (
                  <button
                    key={g.id}
                    type="button"
                    disabled={busy !== null}
                    onClick={() => (many ? toggle(g) : pick(g))}
                    title={prompt}
                    className="group relative aspect-square overflow-hidden rounded-xl bg-surface-3 disabled:opacity-60"
                  >
                    {kind === "video" ? (
                      <video src={src} className="size-full object-cover" muted playsInline preload="metadata" />
                    ) : (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={src} alt="" className="size-full object-cover" />
                    )}
                    <span className={`absolute inset-0 ring-lime transition group-hover:ring-2 ${selected.includes(g.id) ? "ring-2" : ""}`} />
                    {selected.includes(g.id) && (
                      <span className="absolute top-1.5 right-1.5 flex size-6 items-center justify-center rounded-full bg-lime text-xs font-bold text-ink">
                        {selected.indexOf(g.id) + 1}
                      </span>
                    )}
                    {busy === g.id && (
                      <span className="absolute inset-0 flex items-center justify-center bg-black/50">
                        <Loader2 className="size-6 animate-spin text-lime" />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        {many && (
          <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3">
            <span className="text-sm text-fg-3">{r.selected(selected.length, max)}</span>
            <button
              type="button"
              onClick={addSelected}
              disabled={selected.length === 0 || busy !== null}
              className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink disabled:opacity-40"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
              {r.add(selected.length)}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
