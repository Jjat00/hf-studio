"use client";

import clsx from "clsx";
import { Bookmark, ImageIcon, Video } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { localizePreset, presetCategory } from "@/lib/i18n/presets";
import { studio } from "@/lib/studio";
import type { Preset } from "@/lib/types";

const FALLBACK = { video: "/art/text-to-video.webp", image: "/art/text-to-image.webp" };

export default function PresetsPage() {
  const { t, locale } = useI18n();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    studio.presets().then((r) => setPresets(r.presets)).catch((e) => setError(e.message));
  }, []);
  const categories = useMemo(() => [null, ...new Set(presets.map((p) => p.category))], [presets]);
  const shown = presets.filter((p) => category === null || p.category === category).map((p) => localizePreset(p, locale));

  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{t.presets.title}</h1>
      <p className="mt-2 max-w-2xl text-fg-3">{t.presets.body}</p>
      <div className="hide-scrollbar mt-6 flex gap-1.5 overflow-x-auto">
        {categories.map((c) => (
          <button
            key={c ?? "all"}
            type="button"
            onClick={() => setCategory(c)}
            className={clsx(
              "h-9 shrink-0 rounded-xl px-3.5 text-sm font-medium transition-colors",
              category === c ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg",
            )}
          >
            {c === null ? t.presets.all : presetCategory(c, locale)}
          </button>
        ))}
      </div>
      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {shown.map((p) => {
          const Kind = p.output === "image" ? ImageIcon : Video;
          return (
            <Link key={p.slug} href={`/presets/${p.slug}`} className="group block">
              <div className="grain relative aspect-[16/10] overflow-hidden rounded-[18px] bg-surface-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={p.cover ?? FALLBACK[p.output]}
                  alt=""
                  className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                />
                <span className="absolute top-3 left-3 flex items-center gap-1.5 rounded-lg bg-black/60 px-2 py-1 text-xs font-medium backdrop-blur">
                  <Kind className="size-3.5" /> {p.output === "image" ? t.kinds.Image : t.kinds.Video}
                </span>
                {!p.builtin && (
                  <span className="absolute top-3 right-3 flex items-center gap-1 rounded-lg bg-lime px-2 py-1 text-xs font-bold text-ink">
                    <Bookmark className="size-3.5" /> {t.presets.mine}
                  </span>
                )}
              </div>
              <p className="mt-3 font-mono text-[13px] text-fg-3">/{p.slug}</p>
              <p className="headline mt-1 text-[20px] tracking-[-0.03em]">{p.title}</p>
              <p className="mt-1 text-[15px] leading-snug text-fg-3">{p.description}</p>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
