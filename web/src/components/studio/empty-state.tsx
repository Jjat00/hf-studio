"use client";

import { Download, Plus, RotateCcw, Bookmark, Trash2, Video } from "lucide-react";
import { useI18n } from "@/components/i18n-provider";
import type { EmptyState as Empty } from "@/lib/modes";

/** Estado vacío / «How it works» con los tres pasos ilustrados, como en Higgsfield. */
export function EmptyState({ empty, art, notes }: { empty: Empty; art: string; notes?: string[] }) {
  const { t, pick } = useI18n();
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col items-center px-6 py-14">
      <h2 className="headline max-w-4xl text-center text-4xl md:text-[56px]">{pick(empty.title)}</h2>
      <div className="mt-12 grid w-full grid-cols-1 gap-6 md:grid-cols-3">
        {empty.steps.map((step, i) => (
          <div key={i} className="flex flex-col items-center text-center">
            <div className="relative h-[250px] w-full overflow-hidden rounded-[28px] border border-line bg-surface-2">
              {i === 0 && <StepInput />}
              {i === 1 && <StepPrompt />}
              {i === 2 && <StepResult art={art} />}
            </div>
            <span className="mt-5 rounded-lg bg-surface-4 px-2.5 py-1 text-sm font-medium">{t.empty.step(i + 1)}</span>
            <h3 className="headline mt-3 text-[26px]">{pick(step.title)}</h3>
            <p className="mt-2 max-w-xs text-[15px] leading-relaxed text-fg-3">{pick(step.body)}</p>
          </div>
        ))}
      </div>
      {notes && notes.length > 0 && (
        <div className="mt-12 w-full max-w-3xl rounded-card border border-line bg-surface-2 p-5">
          <p className="mb-2 text-sm font-semibold">
            {t.empty.modelNotes}
            {t.empty.externalNote && <span className="font-normal text-fg-3"> · {t.empty.externalNote}</span>}
          </p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-fg-2">
            {notes.map((n) => (
              <li key={n}>{n.replace(/\\_/g, "_")}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StepInput() {
  const { t } = useI18n();
  return (
    <div className="absolute inset-x-5 top-8 bottom-0 rounded-t-2xl border border-line bg-surface-3 p-3">
      <p className="mb-3 text-center text-xs text-fg-2">{t.empty.uploadReference}</p>
      <div className="grid grid-cols-2 gap-2">
        {[
          { icon: Video, title: t.empty.uploadVideo, sub: t.empty.referenceClip },
          { icon: Plus, title: t.empty.addElements, sub: t.empty.upToFour },
        ].map(({ icon: Icon, title, sub }) => (
          <div key={title} className="flex h-36 flex-col items-center justify-center gap-2 rounded-xl bg-surface-4">
            <span className="flex size-11 items-center justify-center rounded-full bg-surface-5">
              <Icon className="size-5" />
            </span>
            <p className="text-[13px] font-semibold">{title}</p>
            <p className="text-[10px] text-fg-3">{sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function StepPrompt() {
  const [before, lit, after] = useI18n().t.empty.demo;
  return (
    <div className="absolute inset-0 p-7 text-left text-[27px] leading-snug font-medium text-fg-4">
      {before}
      <span className="text-fg-2">{lit}</span>
      {after}
      <span className="ml-1 inline-block h-7 w-0.5 translate-y-1 animate-pulse bg-fg" />
    </div>
  );
}

function StepResult({ art }: { art: string }) {
  return (
    <div className="absolute inset-x-5 top-5 bottom-5 overflow-hidden rounded-2xl">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={art} alt="" className="size-full object-cover" />
      <div className="absolute inset-x-6 bottom-3 flex justify-around rounded-xl bg-black/70 py-2 backdrop-blur">
        {[Download, RotateCcw, Bookmark, Trash2].map((Icon, i) => (
          <Icon key={i} className="size-4 text-fg-2" />
        ))}
      </div>
    </div>
  );
}
