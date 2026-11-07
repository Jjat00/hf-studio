"use client";

import clsx from "clsx";
import { FolderOpen, Loader2, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { setActiveProject, useActiveProject } from "@/lib/project";
import { studio } from "@/lib/studio";
import type { ProjectSummary } from "@/lib/types";

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

/** Proyectos: lista con portada, crear uno y elegir el activo. */
export function ProjectList() {
  const { t } = useI18n();
  const p = t.projects;
  const active = useActiveProject();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    studio.projects().then(
      (r) => setProjects(r.projects),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, []);

  async function create() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const made = await studio.createProject(name.trim(), description.trim());
      setProjects((list) => [made, ...(list ?? [])]);
      setActiveProject({ id: made.id, name: made.name });
      setName("");
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-4 py-8 md:px-8">
      <h1 className="headline text-[40px] md:text-[56px]">{p.title}</h1>
      <p className="mt-2 max-w-3xl text-fg-3">{p.subtitle}</p>

      <form
        className="mt-6 flex flex-wrap gap-2 rounded-2xl border border-line bg-surface-2 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={120}
          placeholder={p.namePlaceholder}
          className="h-10 min-w-0 flex-1 rounded-xl border border-line-2 bg-surface-3 px-3 text-sm outline-none focus:border-lime/60"
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={300}
          placeholder={p.descriptionPlaceholder}
          className="h-10 min-w-0 flex-[2] rounded-xl border border-line-2 bg-surface-3 px-3 text-sm outline-none focus:border-lime/60"
        />
        <button
          type="submit"
          disabled={!name.trim() || busy}
          className="flex h-10 items-center gap-1.5 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-40"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {p.create}
        </button>
      </form>
      <p className="mt-2 text-xs text-fg-3">{p.activeHint}</p>

      {error && <p className="mt-4 rounded-2xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {projects === null ? (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="shimmer aspect-video rounded-2xl" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <p className="mt-16 text-center text-fg-3">{p.empty}</p>
      ) : (
        <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {projects.map((pr) => {
            const on = active?.id === pr.id;
            return (
              <li key={pr.id} className={clsx("rounded-2xl border bg-surface-2 p-2.5", on ? "border-lime/60" : "border-line")}>
                <Link href={`/projects/${pr.id}`} className="block">
                  <ProjectCover project={pr} />
                  <div className="mt-2.5 flex items-center gap-2 px-1">
                    <p className="min-w-0 flex-1 truncate font-semibold text-fg">{pr.name}</p>
                    {on && <span className="rounded-md bg-lime/15 px-1.5 py-0.5 text-[11px] font-bold text-lime">{p.active}</span>}
                  </div>
                  <p className="truncate px-1 text-xs text-fg-3">{pr.description || p.generations(pr.generations)}</p>
                </Link>
                <button
                  type="button"
                  onClick={() => setActiveProject(on ? null : { id: pr.id, name: pr.name })}
                  className={clsx(
                    "mt-2 h-8 w-full rounded-lg text-xs font-semibold transition-colors",
                    on ? "bg-surface-4 text-fg-2 hover:text-fg" : "bg-lime/10 text-lime hover:bg-lime/20",
                  )}
                >
                  {on ? p.deactivate : p.activate}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
