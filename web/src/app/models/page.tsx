"use client";

import clsx from "clsx";
import { ExternalLink, ImageIcon, Search, Video } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { matchesModel, workflowLabel } from "@/lib/i18n/workflow";
import { modelLabel, studio } from "@/lib/studio";
import type { ModelSummary } from "@/lib/types";

const CAPS = [
  "",
  "text-to-video",
  "image-to-video",
  "first-last-frame",
  "video-input",
  "reference-to-video",
  "video-edit",
  "video-extend",
  "motion-transfer",
  "text-to-image",
  "edit",
] as const;

export default function ModelsPage() {
  const { t, locale } = useI18n();
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [synced, setSynced] = useState("");
  const [cap, setCap] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    studio
      .models()
      .then((r) => {
        setModels(r.models);
        setSynced(r.synced_at);
      })
      .catch((e) => setError(e.message));
  }, []);
  const shown = useMemo(
    () =>
      models.filter(
        (m) => (!cap || m.capabilities.includes(cap)) && matchesModel(m, q, locale),
      ),
    [models, cap, q, locale],
  );
  return (
    <div className="px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline text-[40px] md:text-[56px]">{t.models.title}</h1>
          <p className="mt-2 text-fg-3">{t.models.subtitle(models.length, synced)}</p>
        </div>
        <label className="flex h-11 w-full max-w-xs items-center gap-2 rounded-xl border border-line bg-surface-2 px-3">
          <Search className="size-4 text-fg-3" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.models.search} className="flex-1 bg-transparent outline-none" />
        </label>
      </div>
      <div className="hide-scrollbar mt-6 flex gap-1.5 overflow-x-auto">
        {CAPS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setCap(key)}
            className={clsx(
              "h-9 shrink-0 rounded-xl px-3.5 text-sm font-medium transition-colors",
              cap === key ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg",
            )}
          >
            {t.models.caps[key]}
          </button>
        ))}
      </div>
      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {shown.map((m) => {
          const { name, workflow } = modelLabel(m.title);
          const Icon = m.output === "image" ? ImageIcon : Video;
          const page = m.output === "image" ? "image" : "video";
          return (
            <div key={m.id} className="flex flex-col rounded-[22px] border border-line bg-surface-2 p-5">
              <div className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-1.5 rounded-xl bg-surface-4 px-2.5 py-1 text-sm font-medium text-fg-2">
                  <Icon className="size-4" /> {m.output === "image" ? t.kinds.Image : t.kinds.Video}
                </span>
                <a href={m.docs_url} target="_blank" rel="noreferrer" className="text-fg-3 hover:text-fg" aria-label={t.models.docs}>
                  <ExternalLink className="size-4" />
                </a>
              </div>
              <p className="mt-4 text-[19px] font-semibold">{name}</p>
              <p className="text-[15px] text-fg-3">{workflowLabel(workflow, locale)}</p>
              <p className="mt-2 truncate font-mono text-[11px] text-fg-4">{m.id}</p>
              <div className="mt-3 flex flex-wrap gap-1">
                {m.capabilities.slice(0, 5).map((c) => (
                  <span key={c} className="rounded-md bg-glass px-1.5 py-0.5 text-[11px] text-fg-2">
                    {t.capabilities[c] ?? c}
                  </span>
                ))}
              </div>
              {m.output !== "unknown" && (
                <Link
                  href={`/${page}?model=${encodeURIComponent(m.id)}`}
                  className="mt-4 rounded-xl bg-surface-4 py-2.5 text-center text-sm font-semibold transition-colors hover:bg-lime hover:text-ink"
                >
                  {t.models.useModel}
                </Link>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
