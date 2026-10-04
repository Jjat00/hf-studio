"use client";

import clsx from "clsx";
import { Check, Shapes, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { apiSrc, studio } from "@/lib/studio";
import type { StudioElement } from "@/lib/types";

const MAX = 3; // APIMart y KIE admiten hasta 3 elementos por tarea

/** Selector de elementos de HF Studio para el campo `elements` de Kling 3.0. Elegir uno añade su @nombre
 *  al prompt; los ids de Higgsfield que ya traiga la entrada (p. ej. al reutilizar) se muestran tal cual. */
export function ElementPicker({
  value,
  onChange,
  onPick,
}: {
  value: string[] | undefined;
  onChange: (v: string[]) => void;
  onPick: (el: StudioElement) => void;
}) {
  const { t } = useI18n();
  const e = t.elements;
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const selected = value ?? [];

  useEffect(() => {
    studio.elements().then((r) => setElements(r.elements), () => setElements([]));
  }, []);

  const known = new Set((elements ?? []).map((el) => el.id));
  const foreign = selected.filter((id) => !known.has(id) && elements !== null);

  function toggle(el: StudioElement) {
    if (selected.includes(el.id)) {
      onChange(selected.filter((id) => id !== el.id));
    } else if (selected.length < MAX) {
      onChange([...selected, el.id]);
      onPick(el);
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-fg-2">
          <Shapes className="size-4" />
          {e.pickerTitle}
          {selected.length > 0 && <span className="font-normal text-fg-3">({selected.length}/{MAX})</span>}
        </span>
        <Link href="/elements" className="text-xs text-fg-3 hover:text-fg">
          {e.manage}
        </Link>
      </div>
      <p className="mt-1 text-xs text-fg-3">{e.pickerHint}</p>
      {elements === null ? (
        <div className="shimmer mt-3 h-16 rounded-xl" />
      ) : elements.length === 0 ? (
        <Link href="/elements" className="mt-3 inline-block text-sm text-lime hover:underline">
          {e.create}
        </Link>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {elements.map((el) => {
            const on = selected.includes(el.id);
            const full = !on && selected.length >= MAX;
            return (
              <button
                key={el.id}
                type="button"
                onClick={() => toggle(el)}
                disabled={full}
                title={full ? e.max : el.description}
                className={clsx(
                  "flex items-center gap-2 rounded-xl border py-1 pr-3 pl-1 text-sm transition-colors disabled:opacity-40",
                  on ? "border-lime bg-lime/10 text-fg" : "border-line bg-surface-3 text-fg-2 hover:text-fg",
                )}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={apiSrc(el.images[0])} alt="" className="size-8 rounded-lg object-cover" />
                <span className="font-mono">{el.mention}</span>
                {on && <Check className="size-3.5 text-lime" />}
              </button>
            );
          })}
        </div>
      )}
      {foreign.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {foreign.map((id) => (
            <span key={id} className="flex items-center gap-1 rounded-md bg-glass px-1.5 py-0.5 font-mono text-xs text-fg-2">
              {id}
              <button type="button" aria-label={e.remove} onClick={() => onChange(selected.filter((x) => x !== id))}>
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
