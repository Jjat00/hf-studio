"use client";

import clsx from "clsx";
import { Check, Film, ImageIcon, LayoutGrid, Loader2, Rows3, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Lightbox } from "@/components/lightbox";
import { outputSrc, studio, type Shot, type ShotStatus, type ShotTake } from "@/lib/studio";

const STATUSES: ShotStatus[] = ["planned", "boarded", "proposed", "generating", "review", "approved", "retake", "cut"];
const TONE: Record<ShotStatus, string> = {
  planned: "bg-surface-4 text-fg-3",
  boarded: "bg-sky-400/15 text-sky-300",
  proposed: "bg-violet-400/15 text-violet-300",
  generating: "bg-warning/15 text-warning",
  review: "bg-amber-400/15 text-amber-300",
  approved: "bg-success/15 text-success",
  retake: "bg-danger/15 text-danger",
  cut: "bg-surface-4 text-fg-4 line-through",
};

const src = (take: ShotTake | null) => (take?.url ? outputSrc({ url: take.url, file_url: take.file_url ?? undefined }) : null);

/** Fotograma que representa la toma: la toma elegida, si no el storyboard, si no la última toma terminada. */
function cover(shot: Shot): ShotTake | null {
  const done = [...shot.takes].reverse().find((t) => t.status === "completed" && t.url);
  return shot.selected?.url ? shot.selected : shot.board?.url ? shot.board : (done ?? null);
}

function Frame({ take, className, onOpen }: { take: ShotTake | null; className?: string; onOpen?: () => void }) {
  const { t } = useI18n();
  const url = src(take);
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!url}
      className={clsx("relative flex shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-4 text-fg-4 enabled:hover:ring-2 enabled:hover:ring-lime/50", className)}
    >
      {!url ? (
        <span className="flex flex-col items-center gap-1 text-[11px]">
          <ImageIcon className="size-4" />
          {t.production.noBoard}
        </span>
      ) : take?.kind === "video" ? (
        <video src={url} className="size-full object-cover" muted playsInline preload="metadata" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" />
      )}
      {take?.kind === "video" && url && <Film className="absolute right-1 bottom-1 size-3.5 text-white drop-shadow" />}
    </button>
  );
}

function StatusChip({ status }: { status: ShotStatus }) {
  const { t } = useI18n();
  return <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap", TONE[status])}>{t.production.status[status]}</span>;
}

/**
 * Lista de tomas del proyecto (la escribe AI Director con `upsert_shots`): tabla por escena con estado, storyboard,
 * tomas generadas (se elige la buena con un clic) y notas, o la misma lista como tira de storyboard.
 */
export function ShotList({ projectId, revision, mode, onMode }: { projectId: string; revision: number; mode: "table" | "storyboard"; onMode: (m: "table" | "storyboard") => void }) {
  const { t } = useI18n();
  const p = t.production;
  const [shots, setShots] = useState<Shot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ items: ShotTake[]; start: number } | null>(null);

  const load = useCallback(() => {
    studio.shots(projectId).then(
      (r) => setShots(r.shots),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [projectId]);

  useEffect(() => load(), [load, revision]);

  // Mientras alguna toma se genera, se relee cada pocos segundos (pasa sola a «En revisión»).
  const busy = shots?.some((s) => s.status === "generating") ?? false;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
  }, [busy, load]);

  const scenes = useMemo(() => {
    const groups = new Map<string, Shot[]>();
    for (const s of shots ?? []) groups.set(s.scene, [...(groups.get(s.scene) ?? []), s]);
    return [...groups.entries()];
  }, [shots]);

  async function patch(shot: Shot, change: Parameters<typeof studio.updateShot>[1]) {
    try {
      const next = await studio.updateShot(shot.id, change);
      setShots((list) => list?.map((s) => (s.id === shot.id ? next : s)) ?? list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(shot: Shot) {
    if (!window.confirm(p.confirmDeleteShot(shot.number || shot.scene))) return;
    try {
      await studio.deleteShot(shot.id);
      setShots((list) => list?.filter((s) => s.id !== shot.id) ?? list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const open = (items: (ShotTake | null)[], take: ShotTake | null) => {
    const usable = items.filter((x): x is ShotTake => Boolean(x?.url));
    const start = Math.max(0, usable.findIndex((x) => x.job_id === take?.job_id));
    if (usable.length) setViewing({ items: usable, start });
  };

  if (shots === null) return error ? <p className="text-sm text-danger">{error}</p> : <Loader2 className="m-4 size-5 animate-spin text-fg-3" />;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-4 flex items-center gap-2">
        <div className="flex rounded-lg bg-surface-3 p-0.5">
          {(["table", "storyboard"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onMode(m)}
              className={clsx("flex h-8 items-center gap-1.5 rounded-md px-3 text-sm font-medium", mode === m ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg")}
            >
              {m === "table" ? <Rows3 className="size-4" /> : <LayoutGrid className="size-4" />}
              {m === "table" ? p.table : p.storyboard}
            </button>
          ))}
        </div>
        <span className="text-sm text-fg-3">{shots.length > 0 && p.takes(shots.reduce((n, s) => n + s.takes.length, 0))}</span>
      </div>
      {error && <p className="mb-3 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {shots.length === 0 && <p className="mt-16 text-center text-fg-3">{p.noShots}</p>}

      {scenes.map(([scene, list]) => (
        <section key={scene} className="mb-8">
          <h3 className="mb-3 text-[15px] font-semibold text-fg">{p.scene(scene)}</h3>
          {mode === "storyboard" ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {list.map((shot) => {
                const c = cover(shot);
                return (
                  <div key={shot.id} className="overflow-hidden rounded-xl border border-line bg-surface-2">
                    <Frame take={c} className="aspect-video w-full rounded-none" onOpen={() => open([shot.board, ...shot.takes], c)} />
                    <div className="space-y-1 p-2.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-fg-3">{shot.number}</span>
                        {shot.shot_size && <span className="text-xs text-fg-4">{shot.shot_size}</span>}
                        <span className="ml-auto">
                          <StatusChip status={shot.status} />
                        </span>
                      </div>
                      <p className="line-clamp-2 text-sm text-fg-2">{shot.purpose}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface-2">
              {list.map((shot) => (
                <ShotRow key={`${shot.id}:${shot.updated_at}`} shot={shot} onPatch={(c) => void patch(shot, c)} onDelete={() => void remove(shot)} onOpen={(take) => open([shot.board, ...shot.takes], take)} />
              ))}
            </div>
          )}
        </section>
      ))}
      {viewing && <Lightbox items={viewing.items.map((x) => ({ src: src(x) ?? "", kind: x.kind === "video" ? "video" : "image" }))} start={viewing.start} onClose={() => setViewing(null)} />}
    </div>
  );
}

function ShotRow({ shot, onPatch, onDelete, onOpen }: { shot: Shot; onPatch: (c: Parameters<typeof studio.updateShot>[1]) => void; onDelete: () => void; onOpen: (t: ShotTake | null) => void }) {
  const { t } = useI18n();
  const p = t.production;
  const [notes, setNotes] = useState(shot.notes);
  return (
    <div className="flex flex-col gap-3 p-3 md:flex-row">
      <Frame take={shot.board ?? null} className="aspect-video w-full md:w-40" onOpen={() => onOpen(shot.board)} />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold text-fg">{shot.number || "–"}</span>
          {shot.shot_size && <span className="rounded bg-surface-4 px-1.5 py-0.5 text-[11px] text-fg-2">{shot.shot_size}</span>}
          {shot.duration_s != null && <span className="text-xs text-fg-3">{shot.duration_s} s</span>}
          {typeof shot.params.camera_movement === "string" && <span className="text-xs text-fg-3">{shot.params.camera_movement}</span>}
          <select
            value={shot.status}
            onChange={(e) => onPatch({ status: e.target.value as ShotStatus })}
            aria-label={t.cinemaStudio.status}
            className={clsx("ml-auto h-7 rounded-full px-2 text-[11px] font-semibold outline-none", TONE[shot.status])}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {p.status[s]}
              </option>
            ))}
          </select>
          <button type="button" title={p.deleteShot} aria-label={p.deleteShot} onClick={onDelete} className="rounded p-1 text-fg-4 hover:text-danger">
            <Trash2 className="size-4" />
          </button>
        </div>
        <p className="text-sm text-fg-2">{shot.purpose}</p>
        {shot.screen_direction && <p className="text-xs text-fg-4">{shot.screen_direction}</p>}
        {shot.takes.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {shot.takes.map((take) => {
              const chosen = shot.selected_job_id === take.job_id;
              return (
                <div key={take.job_id} className={clsx("relative rounded-lg", chosen && "ring-2 ring-lime")}>
                  <Frame take={take} className="h-14 w-24" onOpen={() => onOpen(take)} />
                  {take.status === "completed" ? (
                    <button
                      type="button"
                      title={chosen ? p.selectedTake : p.circleTake}
                      aria-label={chosen ? p.selectedTake : p.circleTake}
                      onClick={() => onPatch({ selected_job_id: chosen ? "" : take.job_id })}
                      className={clsx("absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full border", chosen ? "border-lime bg-lime text-ink" : "border-line-2 bg-surface-1 text-fg-4 hover:text-fg")}
                    >
                      <Check className="size-3" />
                    </button>
                  ) : (
                    <span className="absolute inset-x-0 bottom-0 bg-black/60 px-1 text-center text-[10px] text-white">{take.status}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {shot.verdict && (
          <p className="text-xs text-fg-3">
            <span className="font-semibold text-fg-2">{p.verdict}:</span> {shot.verdict}
          </p>
        )}
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== shot.notes && onPatch({ notes })}
          placeholder={p.notes}
          rows={1}
          maxLength={4000}
          className="w-full resize-y rounded-lg border border-line-2 bg-surface-3 px-2 py-1.5 text-sm outline-none focus:border-lime/50"
        />
      </div>
    </div>
  );
}
