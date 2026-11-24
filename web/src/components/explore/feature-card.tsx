"use client";

import { Brush, Clapperboard, Clock, Film, ImageIcon, Layers, Move, Repeat, Sparkles, SquareTerminal, UserRound, Wand2, BarChart3, Video, Bot, Workflow } from "lucide-react";
import Link from "next/link";
import { useI18n } from "@/components/i18n-provider";
import type { Feature } from "@/lib/features";

const ICONS = { bars: BarChart3, frames: Film, layers: Layers, wand: Wand2, clock: Clock, swap: Repeat, move: Move, sparkles: Sparkles, brush: Brush, terminal: SquareTerminal, user: UserRound, workflow: Workflow, clapper: Clapperboard };
const KIND_ICON = { Video, Image: ImageIcon, Agents: Bot };

/** Tarjeta compacta de la portada: icono, chip de tipo, título con insignia y descripción. */
export function FeatureCard({ f }: { f: Feature }) {
  const { t, pick } = useI18n();
  const Icon = ICONS[f.icon];
  // Como las de Higgsfield (2026-11): icono arriba a la izquierda, insignia arriba a la derecha y el texto abajo.
  return (
    <Link
      href={f.href}
      title={t.kinds[f.kind]}
      className="group flex min-h-[148px] flex-col rounded-[18px] border border-line bg-surface-2 p-4 transition-colors hover:border-line-2 hover:bg-surface-3"
    >
      <div className="flex items-start justify-between gap-2">
        <Icon className="size-5 text-fg-2 group-hover:text-lime" strokeWidth={2.2} />
        {f.badge && (
          <span
            className={
              f.badge === "TOP"
                ? "rounded-md bg-pink px-1.5 py-0.5 text-[11px] font-extrabold text-white italic"
                : "rounded-md bg-lime px-1.5 py-0.5 text-[11px] font-extrabold text-ink italic"
            }
          >
            {t.badges[f.badge]}
          </span>
        )}
      </div>
      <div className="mt-auto pt-4">
        <p className="text-[15px] leading-tight font-semibold tracking-[-0.01em]">{pick(f.title)}</p>
        <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-fg-3">{pick(f.description)}</p>
      </div>
    </Link>
  );
}

/** Tarjeta grande con ilustración y pie en mayúsculas (fila superior de la portada). */
export function BannerCard({ f }: { f: Feature }) {
  const { pick } = useI18n();
  return (
    <Link href={f.href} className="group block w-[78vw] shrink-0 snap-start sm:w-auto">
      <div className="grain relative aspect-[16/9] overflow-hidden rounded-[18px] bg-surface-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={f.art} alt="" className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]" />
      </div>
      <p className="headline mt-3 text-[17px] tracking-[-0.02em] uppercase">{pick(f.title)}</p>
      <p className="mt-0.5 truncate text-[14px] text-fg-3">{pick(f.description)}</p>
    </Link>
  );
}

/** Tarjeta de app de un clic: imagen vertical con «Recrear» al pasar el ratón, como los efectos de Higgsfield. */
export function AppCard({ f }: { f: Feature }) {
  const { t, pick } = useI18n();
  const KindIcon = KIND_ICON[f.kind];
  return (
    <Link href={f.href} className="group block">
      <div className="grain relative aspect-[16/10] overflow-hidden rounded-[18px] bg-surface-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={f.art} alt="" className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.04]" />
        <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-transparent" />
        <span className="absolute top-2.5 left-2.5 flex items-center gap-1 rounded-lg bg-black/55 px-2 py-1 text-[12px] font-medium backdrop-blur">
          <KindIcon className="size-3.5" /> {t.kinds[f.kind]}
        </span>
        <div className="absolute inset-x-3 bottom-3">
          <p className="headline text-[15px] leading-tight uppercase">{pick(f.title)}</p>
          <p className="text-[13px] text-white/75">{pick(f.description)}</p>
          <span className="mt-2 inline-flex items-center gap-1 rounded-lg bg-lime px-2.5 py-1 text-[13px] font-semibold text-ink opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            <Sparkles className="size-3.5" /> {t.explore.recreate}
          </span>
        </div>
      </div>
    </Link>
  );
}
