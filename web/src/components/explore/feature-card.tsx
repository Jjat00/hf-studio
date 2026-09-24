import { Brush, Clock, Film, ImageIcon, Layers, Move, Repeat, Sparkles, SquareTerminal, Wand2, BarChart3, Video, Bot } from "lucide-react";
import Link from "next/link";
import type { Feature } from "@/lib/features";

const ICONS = { bars: BarChart3, frames: Film, layers: Layers, wand: Wand2, clock: Clock, swap: Repeat, move: Move, sparkles: Sparkles, brush: Brush, terminal: SquareTerminal };
const KIND_ICON = { Video, Image: ImageIcon, Agents: Bot };

/** Tarjeta compacta de la portada: icono, chip de tipo, título con insignia y descripción. */
export function FeatureCard({ f }: { f: Feature }) {
  const Icon = ICONS[f.icon];
  const KindIcon = KIND_ICON[f.kind];
  return (
    <Link
      href={f.href}
      className="group flex min-h-[188px] flex-col rounded-[22px] border border-line bg-surface-2 p-5 transition-colors hover:border-line-2 hover:bg-surface-3"
    >
      <div className="flex items-start justify-between">
        <Icon className="size-6 text-fg" strokeWidth={2.2} />
        <span className="flex items-center gap-1.5 rounded-xl bg-surface-4 px-2.5 py-1.5 text-[15px] font-medium text-fg-2">
          <KindIcon className="size-4" /> {f.kind}
        </span>
      </div>
      <div className="mt-auto">
        <p className="flex items-center gap-2 text-[19px] font-semibold tracking-[-0.01em]">
          <span className="truncate">{f.title}</span>
          {f.badge && (
            <span
              className={
                f.badge === "TOP"
                  ? "rounded-md bg-pink px-1.5 py-0.5 text-[13px] font-extrabold text-white italic"
                  : "rounded-md bg-lime px-1.5 py-0.5 text-[13px] font-extrabold text-ink italic"
              }
            >
              {f.badge}
            </span>
          )}
        </p>
        <p className="mt-1.5 text-[15px] leading-snug text-fg-3">{f.description}</p>
      </div>
    </Link>
  );
}

/** Tarjeta grande con ilustración y pie en mayúsculas (fila superior de la portada). */
export function BannerCard({ f }: { f: Feature }) {
  return (
    <Link href={f.href} className="group block">
      <div className="grain relative aspect-[16/9] overflow-hidden rounded-[18px] bg-surface-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={f.art} alt="" className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]" />
      </div>
      <p className="headline mt-4 text-[20px] tracking-[-0.03em]">{f.title}</p>
      <p className="mt-1 text-[16px] text-fg-3">{f.description}</p>
    </Link>
  );
}

