"use client";

import clsx from "clsx";
import { Bot, ImageIcon, MonitorPlay, Video } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { CATEGORIES, USE_CASES, type Category, type Channel } from "@/lib/use-cases";
import { UseCasePanel } from "./use-case-panel";

const CHANNELS = ["all", "ui", "mcp"] as const;

/** Galería de casos de uso; `?case=<slug>` abre el mini tutorial (enlace compartible). */
export function UseCaseGallery() {
  const { t, pick } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [category, setCategory] = useState<Category | null>(null);
  const [channel, setChannel] = useState<"all" | Channel>("all");
  const open = USE_CASES.find((u) => u.slug === params.get("case")) ?? null;
  const shown = USE_CASES.filter(
    (u) => (category === null || u.category === category) && (channel === "all" || u.channels.includes(channel)),
  );
  const select = (slug: string | null) => router.replace(slug ? `${pathname}?case=${slug}` : pathname, { scroll: false });

  const chip = (active: boolean) =>
    clsx("h-9 shrink-0 rounded-xl px-3.5 text-sm font-medium transition-colors", active ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg");

  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{t.useCases.title}</h1>
      <p className="mt-2 max-w-2xl text-fg-3">{t.useCases.body}</p>
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="hide-scrollbar flex gap-1.5 overflow-x-auto">
          {[null, ...CATEGORIES].map((c) => (
            <button key={c ?? "all"} type="button" onClick={() => setCategory(c)} className={chip(category === c)}>
              {t.categories[c ?? "All"]}
            </button>
          ))}
        </div>
        <div className="flex shrink-0 gap-1 rounded-xl bg-surface-2 p-1">
          {CHANNELS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setChannel(c)}
              className={clsx(
                "h-8 rounded-lg px-3 text-sm font-medium transition-colors",
                channel === c ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg",
              )}
            >
              {t.useCases.channels[c]}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {shown.map((u) => {
          const Kind = u.output === "image" ? ImageIcon : Video;
          return (
            <button key={u.slug} type="button" onClick={() => select(u.slug)} className="group block text-left">
              <div className="grain relative aspect-[16/10] overflow-hidden rounded-[18px] bg-surface-3">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={u.art}
                  alt=""
                  loading="lazy"
                  className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                />
                <span className="absolute top-3 left-3 flex items-center gap-1.5 rounded-lg bg-black/60 px-2 py-1 text-xs font-medium backdrop-blur">
                  <Kind className="size-3.5" /> {t.categories[u.category]}
                </span>
                <span className="absolute top-3 right-3 flex gap-1">
                  {u.channels.includes("ui") && (
                    <span className="flex items-center gap-1 rounded-lg bg-black/60 px-2 py-1 text-xs font-medium backdrop-blur">
                      <MonitorPlay className="size-3.5" /> UI
                    </span>
                  )}
                  {u.channels.includes("mcp") && (
                    <span className="flex items-center gap-1 rounded-lg bg-lime px-2 py-1 text-xs font-bold text-ink">
                      <Bot className="size-3.5" /> MCP
                    </span>
                  )}
                </span>
              </div>
              <p className="headline mt-4 text-[20px] tracking-[-0.03em]">{pick(u.title)}</p>
              <p className="mt-1 text-[15px] leading-snug text-fg-3">{pick(u.tagline)}</p>
            </button>
          );
        })}
      </div>

      {open && <UseCasePanel key={open.slug} useCase={open} onClose={() => select(null)} />}
    </div>
  );
}
