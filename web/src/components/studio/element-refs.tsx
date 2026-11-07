"use client";

import clsx from "clsx";
import { Loader2, Shapes } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { apiSrc, studio } from "@/lib/studio";
import type { ElementCategory, StudioElement } from "@/lib/types";

export const CATEGORIES: ElementCategory[] = ["character", "location", "prop", "other"];

/** Lo que un elemento aporta a una generación: sus imágenes vigentes y cómo citarlo en el prompt. */
export type ElementRefs = { element: StudioElement; urls: string[] };

/**
 * Elementos como referencias en cualquier modelo con imágenes de referencia (los que no son Kling 3.0): al elegir uno
 * se añaden sus imágenes a la casilla de referencias y se cita en el prompt. Se agrupan por categoría.
 */
export function ElementRefsPicker({ onAdd, room }: { onAdd: (refs: ElementRefs) => void; room: number }) {
  const { t } = useI18n();
  const e = t.elements;
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const [category, setCategory] = useState<ElementCategory | "all">("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    studio.elements().then((r) => setElements(r.elements), () => setElements([]));
  }, []);

  async function add(el: StudioElement) {
    setBusy(el.id);
    setError(null);
    try {
      const r = await studio.elementUrls(el.id);
      onAdd({ element: el, urls: r.image_urls });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  const shown = (elements ?? []).filter((el) => category === "all" || (el.category ?? "other") === category);
  const present = new Set((elements ?? []).map((el) => el.category ?? "other"));

  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-fg-2">
          <Shapes className="size-4" />
          {e.pickerTitle}
        </span>
        <Link href="/elements" className="text-xs text-fg-3 hover:text-fg">
          {e.manage}
        </Link>
      </div>
      <p className="mt-1 text-xs text-fg-3">{e.refsHint}</p>
      {elements === null ? (
        <div className="shimmer mt-3 h-16 rounded-xl" />
      ) : elements.length === 0 ? (
        <Link href="/elements" className="mt-3 inline-block text-sm text-lime hover:underline">
          {e.create}
        </Link>
      ) : (
        <>
          {present.size > 1 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {(["all", ...CATEGORIES.filter((c) => present.has(c))] as const).map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={clsx("h-7 rounded-lg px-2.5 text-xs font-medium", category === c ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg-2")}
                >
                  {c === "all" ? e.all : e.categories[c]}
                </button>
              ))}
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {shown.map((el) => {
              const full = el.images.length > room;
              return (
                <button
                  key={el.id}
                  type="button"
                  onClick={() => void add(el)}
                  disabled={full || busy !== null}
                  title={full ? e.noRoom : el.description}
                  className="flex items-center gap-2 rounded-xl border border-line bg-surface-3 py-1 pr-3 pl-1 text-sm text-fg-2 transition-colors hover:text-fg disabled:opacity-40"
                >
                  {busy === el.id ? (
                    <Loader2 className="size-8 animate-spin p-2" />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={apiSrc(el.images[0])} alt="" className="size-8 rounded-lg object-cover" />
                  )}
                  <span className="font-mono">{el.mention}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}

/** Texto con el que se cita un elemento en el prompt. Cinema Studio usa <<<image_N>>> (N desde 1) para sus referencias. */
export function elementMention(el: StudioElement, model: string, firstIndex: number): string {
  if (model.startsWith("higgsfield/cinema-studio")) return `${el.name.replace(/_/g, " ")} <<<image_${firstIndex}>>>`;
  return `${el.name.replace(/_/g, " ")} (${el.description})`;
}
