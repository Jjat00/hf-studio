"use client";

import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { studio } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "video", label: "Video" },
  { key: "image", label: "Image" },
  { key: "active", label: "In progress" },
  { key: "failed", label: "Failed" },
] as const;

export default function HistoryPage() {
  const router = useRouter();
  const { items, loading, error, remove } = useGenerations();
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  useEffect(() => {
    studio.models().then((r) => setModels(new Map(r.models.map((m) => [m.id, m])))).catch(() => undefined);
  }, []);

  const shown = useMemo(
    () =>
      items.filter((g) => {
        const out = models.get(g.model)?.output;
        if (filter === "video" || filter === "image") return out === filter;
        if (filter === "active") return !g.terminal;
        if (filter === "failed") return g.terminal && g.status !== "completed";
        return true;
      }),
    [items, models, filter],
  );

  const reuse = (g: Generation) =>
    router.push(`/${models.get(g.model)?.output === "image" ? "image" : "video"}?reuse=${g.id}`);

  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">Library</h1>
      <p className="mt-2 text-fg-3">Everything you and your agents have generated.</p>
      <div className="mt-6 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={clsx(
              "h-10 rounded-xl px-4 text-[15px] font-medium transition-colors",
              filter === f.key ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg-2",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      {loading ? (
        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="shimmer aspect-video rounded-2xl" />
          ))}
        </div>
      ) : shown.length === 0 ? (
        <p className="mt-16 text-center text-fg-3">Nothing here yet.</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {shown.map((g) => (
            <GenerationCard key={g.id} g={g} layout="grid" models={models} onReuse={reuse} onDelete={remove} />
          ))}
        </div>
      )}
    </div>
  );
}
