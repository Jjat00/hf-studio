"use client";

import clsx from "clsx";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import type { KatanaPreset } from "@/lib/studio";
import { KatanaModal } from "./media-sources";

function Panel({ src, poster, label, accent, video = true }: { src: string; poster?: string; label?: string; accent?: boolean; video?: boolean }) {
  return (
    <div className="relative aspect-[9/16] h-48 overflow-hidden rounded-2xl bg-surface-4 md:h-64">
      {src && (video ? (
        <video src={src} poster={poster} muted loop autoPlay playsInline className="absolute inset-0 size-full object-cover" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="absolute inset-0 size-full object-cover" />
      ))}
      {label && (
        <span className={clsx("absolute left-3 top-3 rounded-lg px-3 py-1.5 text-sm font-semibold",
          accent ? "bg-lime text-black" : "bg-black/45 text-white backdrop-blur")}>{label}</span>
      )}
    </div>
  );
}

/** «¿Cómo funciona?»: los 5 pasos de higgsfield.ai/katana, contados para HF Studio y con medios de la galería. */
export function HowItWorks({ presets, onClose, onExplore }: { presets: KatanaPreset[]; onClose: () => void; onExplore: () => void }) {
  const { t } = useI18n();
  const k = t.katana;
  const [n, setN] = useState(0);
  const total = k.howSteps.length;
  const s = k.howSteps[n];
  const complete = presets.filter((p) => p.person_url && p.result_url);
  const full = complete.find((p) => p.id === "daytona-drift") ?? complete[0] ?? presets[0];
  const versions = presets.filter((p) => p.result_url || p.video_url).slice(0, 4);

  let visual: React.ReactNode = null;
  if (n === 0 && presets[0])
    visual = (
      <div className="flex items-end gap-3">
        {presets.slice(0, 3).map((p, i) => (
          <div key={p.id} className={clsx(i === 1 ? "scale-110" : "opacity-70", "transition")}>
            <Panel src={p.video_url} poster={p.thumbnail_url} />
          </div>
        ))}
      </div>
    );
  else if (n === 1 && full)
    visual = (
      <div className="flex gap-3">
        <Panel src={full.video_url} poster={full.thumbnail_url} label={k.original} />
        <Panel src={full.person_url} label={k.yourCharacter} video={false} />
        <Panel src={full.result_url || full.video_url} poster={full.result_thumbnail_url} label={k.finalEdit} accent />
      </div>
    );
  else if (n === 2 && full)
    visual = (
      <div className="grid w-full max-w-2xl grid-cols-[auto_1fr] items-center gap-6">
        <Panel src={full.video_url} poster={full.thumbnail_url} />
        <div className="space-y-2">
          {[0.9, 0.35, 0.7, 0.5, 1, 0.25, 0.8, 0.6].map((v, i) => (
            <div key={i} className="h-3 rounded-full bg-lime/80" style={{ width: `${v * 100}%`, opacity: 0.4 + v * 0.6 }} />
          ))}
        </div>
      </div>
    );
  else if (n === 3)
    visual = (
      <div className="flex gap-3">
        {versions.map((p, i) => (
          <Panel key={p.id} src={p.result_url || p.video_url} poster={p.result_thumbnail_url || p.thumbnail_url} label={`V${i + 1}`} />
        ))}
      </div>
    );
  else if (n === 4)
    visual = (
      <div className="flex items-center gap-2 font-mono text-sm text-fg-2">
        {[k.stepReference, k.stepAssets, k.stepInstructions, k.stepPlan, "Space"].map((x, i, all) => (
          <span key={x} className="flex items-center gap-2">
            <span className={clsx("rounded-xl px-4 py-3", i === all.length - 1 ? "bg-lime text-black" : "bg-surface-5")}>{x}</span>
            {i < all.length - 1 && <span className="text-fg-3">→</span>}
          </span>
        ))}
      </div>
    );

  return (
    <KatanaModal title={k.how} onClose={onClose} wide={false}>
      <div className="flex flex-col items-center gap-4 py-2 text-center">
        <p className="text-sm text-fg-3">{k.howSubtitle}</p>
        <div className="flex min-h-56 w-full items-center justify-center overflow-x-auto md:min-h-72">{visual}</div>
        <p className="text-xs text-fg-3">{k.stepOf(n + 1, total)}</p>
        <p className="text-sm font-semibold tracking-wide text-lime">{s.kicker}</p>
        <h3 className="text-2xl font-black uppercase tracking-tight md:text-3xl">{s.title}</h3>
        <p className="max-w-xl text-fg-2">{s.body}</p>
        <div className="flex gap-3 pt-2">
          {n > 0 && (
            <button type="button" onClick={() => setN(n - 1)} className="h-12 rounded-xl bg-surface-4 px-6 text-[17px] font-semibold hover:bg-white/10">{k.back}</button>
          )}
          <button type="button" onClick={() => (n < total - 1 ? setN(n + 1) : onExplore())}
            className="h-12 rounded-xl bg-lime px-6 text-[17px] font-semibold text-black hover:bg-lime-400">
            {n < total - 1 ? k.continue : k.explore}
          </button>
        </div>
      </div>
    </KatanaModal>
  );
}
