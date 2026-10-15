"use client";

import clsx from "clsx";
import { Check, Palette } from "lucide-react";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio } from "@/lib/studio";
import type { ModelStyle } from "@/lib/types";

/** Selector del estilo de un modelo con catálogo propio (Genjutsu Restyle): su id va en `preset_id`. Los estilos
 *  los publica Higgsfield y cambian sin aviso; un id que ya no está (p. ej. al reutilizar) se muestra tal cual. */
export function StylePicker({
  model,
  value,
  onChange,
  error,
}: {
  model: string;
  value: string | undefined;
  onChange: (v: string | undefined) => void;
  error?: string;
}) {
  const { t } = useI18n();
  const s = t.styles;
  const [styles, setStyles] = useState<ModelStyle[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    studio.styles(model).then(
      (r) => alive && setStyles(r.styles),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [model, attempt]);

  const current = styles?.find((x) => x.id === value);
  const foreign = value && styles && !current ? value : null;

  return (
    <div className={clsx("rounded-2xl border bg-surface-2 p-4", error ? "border-danger/60" : "border-line")}>
      <span className="flex items-center gap-2 text-sm font-semibold text-fg-2">
        <Palette className="size-4" />
        {s.title}
        {current && <span className="font-normal text-fg-3">· {current.name}</span>}
      </span>
      <p className="mt-1 text-xs text-fg-3">{s.hint}</p>
      {failed ? (
        <p className="mt-3 text-sm text-fg-3">
          {s.error}{" "}
          <button
            type="button"
            className="text-lime hover:underline"
            onClick={() => {
              setFailed(false);
              setAttempt((n) => n + 1);
            }}
          >
            {s.retry}
          </button>
        </p>
      ) : styles === null ? (
        <div className="shimmer mt-3 h-28 rounded-xl" />
      ) : (
        <div className="thin-scrollbar mt-3 grid max-h-72 grid-cols-3 gap-2 overflow-y-auto pr-1 sm:grid-cols-4">
          {styles.map((st) => {
            const on = st.id === value;
            return (
              <button
                key={st.id}
                type="button"
                onClick={() => onChange(on ? undefined : st.id)}
                title={st.name}
                className={clsx(
                  "group relative overflow-hidden rounded-xl border text-left transition-colors",
                  on ? "border-lime ring-1 ring-lime" : "border-line hover:border-line-2",
                )}
              >
                {st.preview_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={st.preview_url} alt="" loading="lazy" className="aspect-square w-full object-cover" />
                ) : (
                  <div className="aspect-square w-full bg-surface-3" />
                )}
                <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-1.5 pt-4 pb-1 text-[11px] leading-tight text-white">
                  {st.name}
                </span>
                {on && (
                  <span className="absolute top-1 right-1 rounded-full bg-lime p-0.5 text-black">
                    <Check className="size-3" />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {foreign && <p className="mt-2 font-mono text-xs text-fg-3">{foreign}</p>}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}
