"use client";

import clsx from "clsx";
import { Check, FolderOpen, Pencil, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import type { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Masonry } from "@/components/masonry";
import { Markdown } from "@/components/supercomputer/chat-panel";
import { modelMap, outputOf, reuseHref, studio } from "@/lib/studio";
import type { Generation, ModelSummary, Project, ProjectSummary } from "@/lib/types";

/** Portada de un proyecto: la elegida o un mosaico con sus últimas salidas. */
export function ProjectCover({ project, className }: { project: Pick<ProjectSummary, "cover" | "thumbnails" | "name">; className?: string }) {
  const thumbs = project.cover ? [project.cover] : project.thumbnails.slice(0, 4);
  return (
    <div className={clsx("relative aspect-video overflow-hidden rounded-xl bg-surface-3", className)}>
      {thumbs.length === 0 ? (
        <div className="flex size-full items-center justify-center text-fg-4">
          <FolderOpen className="size-8" />
        </div>
      ) : (
        <div className={clsx("grid size-full gap-0.5", thumbs.length > 1 && "grid-cols-2")}>
          {thumbs.map((src) =>
            /\.(mp4|webm|mov)(\?|$)/i.test(src) ? (
              <video key={src} src={src} muted playsInline className="size-full object-cover" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={src} src={src} alt={project.name} className="size-full object-cover" />
            ),
          )}
        </div>
      )}
    </div>
  );
}

type GenerationList = ReturnType<typeof useGenerations>;
export type AssetKind = "all" | "image" | "video";

/** Generaciones del proyecto (o de una carpeta), con selección para moverlas o usar una como portada. La lista la
 * lleva quien la muestra (así puede añadir al momento lo que se acaba de generar). */
export function AssetGrid({
  project,
  folder,
  list,
  kind = "all",
  columns = 4,
  onCover,
  onSelecting,
  empty,
}: {
  project: Project;
  folder?: string;
  list: GenerationList;
  kind?: AssetKind;
  columns?: number;
  onCover: (cover: string | null) => void;
  onSelecting?: (on: boolean) => void;
  empty?: ReactNode;
}) {
  const { t } = useI18n();
  const p = t.projects;
  const h = t.history;
  const router = useRouter();
  const { items, loading, remove, setFavorite } = list;
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  const [others, setOthers] = useState<ProjectSummary[]>([]);
  const [selecting, setSelectingState] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  // Movidas aquí: desaparecen de la vista al momento (el sondeo lo confirma después).
  const [gone, setGone] = useState<Set<string>>(new Set());
  useEffect(() => {
    studio.models().then((r) => setModels(modelMap(r.models))).catch(() => undefined);
    studio.projects().then((r) => setOthers(r.projects.filter((x) => x.id !== project.id))).catch(() => undefined);
  }, [project.id]);

  function setSelecting(on: boolean) {
    setSelectingState(on);
    onSelecting?.(on);
  }

  const shown = useMemo(
    () =>
      items.filter((g) => {
        if (gone.has(g.id)) return false;
        if (kind === "all") return true;
        return (g.outputs[0]?.kind ?? outputOf(g.model, models)) === kind;
      }),
    [items, gone, kind, models],
  );
  const chosen = shown.filter((g) => picked.has(g.id));

  async function move(target: string) {
    if (!chosen.length || !target) return;
    const [where, value] = target.split(":");
    const ids = chosen.map((g) => g.id);
    try {
      const res =
        where === "folder"
          ? await studio.move(ids, project.id, value === "none" ? null : value)
          : await studio.move(ids, value === "none" ? null : value, null);
      // Sale de la vista lo que ya no corresponde a este proyecto o a la carpeta filtrada.
      const leaves = where === "project" || (folder !== undefined && folder !== value);
      if (leaves) setGone((prev) => new Set([...prev, ...res.changed]));
      setNotice(p.moved(res.changed.length));
      setPicked(new Set());
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }

  async function cover(g: Generation) {
    const out = g.outputs.find((o) => o.kind === "image" || o.kind === "video");
    if (!out) return;
    try {
      await studio.updateProject(project.id, { cover: out.url });
      onCover(out.url);
      setNotice(null);
      setSelecting(false);
      setPicked(new Set());
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    }
  }

  if (loading) return <div className="shimmer h-60 rounded-2xl" />;
  return (
    <>
      {shown.length > 0 && (
        <div className="mb-3 flex justify-end">
          <button
            type="button"
            onClick={() => {
              setSelecting(!selecting);
              setPicked(new Set());
              setNotice(null);
            }}
            className={clsx("h-8 rounded-lg px-3 text-sm font-medium", selecting ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg")}
          >
            {selecting ? h.done : h.select}
          </button>
        </div>
      )}
      {shown.length === 0 ? (
        (empty ?? <p className="mt-12 text-center text-fg-3">{p.nothing}</p>)
      ) : (
        <Masonry
          items={shown}
          itemKey={(g) => g.id}
          maxColumns={columns}
          minColumnWidth={columns > 4 ? 160 : 220}
          gap={12}
          render={(g) => {
            const on = picked.has(g.id);
            return (
              <div className="relative">
                <div inert={selecting}>
                  <GenerationCard
                    g={g}
                    layout="grid"
                    models={models}
                    gallery={shown}
                    onReuse={(x) => router.push(reuseHref(x.model, x.id, models))}
                    onDelete={remove}
                    onFavorite={(x) => void setFavorite([x.id], !x.favorite).catch(() => undefined)}
                  />
                </div>
                {selecting && (
                  <button
                    type="button"
                    aria-pressed={on}
                    aria-label={g.model}
                    onClick={() =>
                      setPicked((prev) => {
                        const next = new Set(prev);
                        if (next.has(g.id)) next.delete(g.id);
                        else next.add(g.id);
                        return next;
                      })
                    }
                    className={clsx("absolute inset-0 rounded-2xl transition", on ? "bg-lime/10 ring-2 ring-lime" : "hover:bg-white/5")}
                  >
                    <span className={clsx("absolute top-3 left-3 flex size-6 items-center justify-center rounded-md border-2", on ? "border-lime bg-lime text-ink" : "border-white/70 bg-black/40")}>
                      {on && <Check className="size-4" />}
                    </span>
                  </button>
                )}
              </div>
            );
          }}
        />
      )}
      {selecting && (
        <div className="fixed inset-x-0 bottom-4 z-30 mx-auto flex w-[min(680px,calc(100vw-2rem))] flex-wrap items-center gap-2 rounded-2xl border border-line-2 bg-surface-3 p-2.5 shadow-2xl">
          <span className="px-2 text-sm font-medium">{h.selected(chosen.length)}</span>
          <select
            value=""
            disabled={!chosen.length}
            onChange={(e) => void move(e.target.value)}
            className="ml-auto h-9 max-w-56 rounded-xl bg-surface-4 px-2 text-sm font-semibold text-fg disabled:opacity-40"
            aria-label={p.moveTo}
          >
            <option value="">{p.moveTo}</option>
            <optgroup label={project.name}>
              <option value="folder:none">{p.folders.unfiled}</option>
              {project.folders.map((f) => (
                <option key={f.id} value={`folder:${f.id}`}>
                  {f.name}
                </option>
              ))}
            </optgroup>
            <optgroup label={t.projects.title}>
              {others.map((o) => (
                <option key={o.id} value={`project:${o.id}`}>
                  {o.name}
                </option>
              ))}
              <option value="project:none">{p.noProject}</option>
            </optgroup>
          </select>
          <button
            type="button"
            disabled={chosen.length !== 1 || chosen[0].status !== "completed"}
            onClick={() => void cover(chosen[0])}
            className="h-9 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-40"
          >
            {p.useAsCover}
          </button>
          <button
            type="button"
            onClick={() => {
              setSelecting(false);
              setPicked(new Set());
            }}
            className="h-9 rounded-xl bg-surface-4 px-3 text-sm font-medium text-fg-2 hover:text-fg"
          >
            {h.done}
          </button>
          {notice && <p className="w-full px-2 text-xs text-fg-3">{notice}</p>}
        </div>
      )}
    </>
  );
}

export type BriefDraft = { text: string; saved: string; state: "saved" | "saving" | "unsaved" };

/**
 * Borrador del brief a nivel de proyecto: cambiar de vista no lo pierde. Se guarda un segundo después de dejar de
 * escribir, con una sola escritura en vuelo: al terminar, si el borrador cambió, se envía el último (nunca uno viejo).
 * Si falla queda «Sin guardar» con reintento; al salir del proyecto se envía lo que falte.
 */
export function useBriefDraft(id: string, onSaved: (p: Project) => void) {
  const [brief, setBrief] = useState<BriefDraft | null>(null);
  const latest = useRef<string | null>(null);
  const server = useRef<string | null>(null);
  const inFlight = useRef(false);

  const init = useCallback((text: string) => {
    latest.current = text;
    server.current = text;
    setBrief({ text, saved: text, state: "saved" });
  }, []);
  const flush = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      while (latest.current !== null && latest.current !== server.current) {
        const text = latest.current;
        setBrief((b) => (b ? { ...b, state: "saving" } : b));
        try {
          const saved = await studio.updateProject(id, { brief: text });
          server.current = text;
          onSaved(saved);
        } catch {
          setBrief((b) => (b ? { ...b, state: "unsaved" } : b));
          return;
        }
      }
      const done = server.current;
      setBrief((b) => (b && done !== null ? { ...b, saved: done, state: b.text === done ? "saved" : "unsaved" } : b));
    } finally {
      inFlight.current = false;
    }
  }, [id, onSaved]);
  const text = brief?.text ?? null;
  useEffect(() => {
    latest.current = text;
    if (text === null || text === server.current) return;
    const timer = setTimeout(() => void flush(), 1000);
    return () => clearTimeout(timer);
  }, [text, flush]);
  useEffect(
    () => () => {
      if (latest.current !== null && latest.current !== server.current) void flush();
    },
    [flush],
  );
  const change = useCallback((value: string) => setBrief((b) => (b ? { ...b, text: value, state: value === b.saved ? "saved" : "unsaved" } : b)), []);
  const retry = useCallback(() => void flush(), [flush]);
  return { brief, init, change, retry };
}

/** Brief en Markdown: el borrador vive en `useBriefDraft`, que lo guarda solo. Vacío, ofrece una plantilla. */
export function BriefEditor({
  draft,
  onChange,
  onRetry,
  template,
}: {
  draft: BriefDraft;
  onChange: (text: string) => void;
  onRetry: () => void;
  template?: string;
}) {
  const { t } = useI18n();
  const b = t.projects.brief;
  const [preview, setPreview] = useState(false);
  return (
    <div className="max-w-4xl">
      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-fg-3">
        <span>{b.hint}</span>
        {draft.state === "unsaved" ? (
          <button type="button" onClick={onRetry} className="ml-auto text-warning hover:underline">
            {b.unsaved} · {b.retry}
          </button>
        ) : (
          <span className="ml-auto flex items-center gap-1.5">
            <span className={clsx("size-2 rounded-full", draft.state === "saved" ? "bg-success" : "bg-warning")} />
            {b[draft.state]}
          </span>
        )}
        <button type="button" onClick={() => setPreview(!preview)} className="rounded-lg bg-surface-4 px-2.5 py-1 font-medium text-fg-2 hover:text-fg">
          {preview ? <Pencil className="size-3.5" /> : "Markdown"}
        </button>
      </div>
      {template && !draft.text.trim() && !preview && (
        <button
          type="button"
          onClick={() => onChange(template)}
          className="mb-2 rounded-lg border border-dashed border-line-2 px-3 py-1.5 text-xs font-medium text-fg-2 hover:border-lime/50 hover:text-fg"
        >
          {b.useTemplate}
        </button>
      )}
      {preview ? (
        <div className="rounded-2xl border border-line bg-surface-2 p-5 text-[15px] leading-relaxed">
          <Markdown text={draft.text} />
        </div>
      ) : (
        <textarea
          value={draft.text}
          onChange={(e) => onChange(e.target.value)}
          rows={24}
          maxLength={50000}
          className="thin-scrollbar w-full rounded-2xl border border-line-2 bg-surface-2 p-5 font-mono text-[14px] leading-relaxed outline-none focus:border-lime/50"
        />
      )}
    </div>
  );
}

export function ProjectSettings({ project, onSaved, onDeleted }: { project: Project; onSaved: (p: Project) => void; onDeleted: () => void }) {
  const { t } = useI18n();
  const s = t.projects.settings;
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const field = "w-full rounded-xl border border-line-2 bg-surface-3 px-3 py-2 text-sm outline-none focus:border-lime/60";

  async function save(patch: { name?: string; description?: string; cover?: string }) {
    setBusy(true);
    setError(null);
    try {
      onSaved(await studio.updateProject(project.id, patch));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(s.confirmDelete(project.name))) return;
    try {
      await studio.deleteProject(project.id);
      onDeleted();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <p className="text-sm font-semibold text-fg-3">{s.details}</p>
      <label className="block space-y-1">
        <span className="text-sm font-medium">{s.name}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className={field} />
      </label>
      <label className="block space-y-1">
        <span className="text-sm font-medium">{s.description}</span>
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} rows={3} className={field} />
      </label>
      <button
        type="button"
        disabled={busy || !name.trim()}
        onClick={() => void save({ name: name.trim(), description })}
        className="h-9 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-40"
      >
        {s.save}
      </button>
      <div className="space-y-2 border-t border-line pt-4">
        <p className="text-sm font-medium">{s.cover}</p>
        <ProjectCover project={project} className="w-72 max-w-full" />
        <p className="text-xs text-fg-3">{s.coverHint}</p>
        {project.cover && (
          <button type="button" onClick={() => void save({ cover: "" })} className="text-sm text-fg-3 hover:text-fg">
            {s.removeCover}
          </button>
        )}
      </div>
      <div className="border-t border-line pt-4">
        <button type="button" onClick={remove} className="flex items-center gap-1.5 text-sm text-danger hover:underline">
          <Trash2 className="size-4" /> {s.delete}
        </button>
      </div>
      {error && <p className="rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
    </div>
  );
}
