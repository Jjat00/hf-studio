"use client";

import { Loader2, Plus, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import type { SpaceSummary } from "@/lib/spaces";
import { apiSrc, studio } from "@/lib/studio";

export function SpacesList() {
  const { t, locale } = useI18n();
  const s = t.spaces;
  const router = useRouter();
  const [items, setItems] = useState<SpaceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    studio.spaces().then(
      (r) => setItems(r.spaces),
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setItems([]);
      },
    );
  }, []);

  async function create() {
    setCreating(true);
    try {
      const space = await studio.createSpace(s.untitled);
      router.push(`/spaces/${space.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setCreating(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm(s.confirmDelete)) return;
    setItems((prev) => prev?.filter((x) => x.id !== id) ?? null);
    await studio.deleteSpace(id).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }

  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline text-[40px] text-lime">{s.title}</h1>
          <p className="mt-1 max-w-2xl text-fg-2">{s.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={create}
          disabled={creating}
          className="flex h-11 items-center gap-2 rounded-xl bg-lime px-4 font-semibold text-ink transition hover:brightness-105 disabled:opacity-60"
        >
          {creating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {s.newSpace}
        </button>
      </div>

      {error && <p className="rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {items === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="shimmer aspect-[4/3] rounded-card" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-line-2 p-12 text-center text-fg-2">
          <Workflow className="size-8 text-fg-3" />
          <p>{s.empty}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((sp) => (
            <div key={sp.id} className="group relative overflow-hidden rounded-card border border-line bg-surface-1">
              <Link href={`/spaces/${sp.id}`} className="block">
                <div className="dotted-bg relative flex aspect-[16/10] items-center justify-center bg-surface-2">
                  {sp.cover ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={apiSrc(sp.cover)} alt="" className="size-full object-cover" />
                  ) : (
                    <Workflow className="size-10 text-fg-4" />
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{sp.title}</p>
                    <p className="text-xs text-fg-3">
                      {s.nodes(sp.nodes)} · {s.edited} {date.format(new Date(sp.updated_at))}
                    </p>
                  </div>
                </div>
              </Link>
              <button
                type="button"
                onClick={() => remove(sp.id)}
                aria-label={s.delete}
                title={s.delete}
                className="absolute top-2 right-2 rounded-lg bg-black/60 p-2 text-fg-2 opacity-0 backdrop-blur transition group-hover:opacity-100 hover:text-danger"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
