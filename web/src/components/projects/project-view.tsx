"use client";

import clsx from "clsx";
import { ArrowLeft, Check, Folder, FolderPlus, MessageSquare, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Masonry } from "@/components/masonry";
import { Markdown } from "@/components/supercomputer/supercomputer";
import { setActiveProject, useActiveProject } from "@/lib/project";
import { modelMap, reuseHref, studio } from "@/lib/studio";
import type { Generation, ModelSummary, Project, ProjectSummary } from "@/lib/types";
import { ProjectCover } from "./project-list";

type Tab = "assets" | "brief" | "settings";

/** Un proyecto: sus generaciones por carpeta, su brief (Markdown, guardado solo) y sus ajustes. */
export function ProjectView({ id }: { id: string }) {
  const { t } = useI18n();
  const p = t.projects;
  const router = useRouter();
  const active = useActiveProject();
  const [project, setProject] = useState<Project | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("assets");
  const [folder, setFolder] = useState<string | undefined>(undefined);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const [brief, setBrief] = useState<BriefDraft | null>(null);
  const latestBrief = useRef<string | null>(null);
  const serverBrief = useRef<string | null>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    studio.project(id).then(
      (pr) => {
        setProject(pr);
        serverBrief.current = pr.brief;
        latestBrief.current = pr.brief;
        setBrief({ text: pr.brief, saved: pr.brief, state: "saved" });
      },
      () => setMissing(true),
    );
  }, [id]);

  // Borrador del brief a nivel de proyecto: cambiar de pestaña no lo pierde. Se guarda un segundo después de dejar de
  // escribir, con una sola escritura en vuelo: al terminar, si el borrador cambió, se envía el último (nunca uno viejo).
  // Si falla queda «Sin guardar» con reintento; al salir del proyecto se envía lo que falte.
  const flushBrief = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      while (latestBrief.current !== null && latestBrief.current !== serverBrief.current) {
        const text = latestBrief.current;
        setBrief((b) => (b ? { ...b, state: "saving" } : b));
        try {
          const saved = await studio.updateProject(id, { brief: text });
          serverBrief.current = text;
          setProject(saved);
        } catch {
          setBrief((b) => (b ? { ...b, state: "unsaved" } : b));
          return;
        }
      }
      const server = serverBrief.current;
      setBrief((b) => (b && server !== null ? { ...b, saved: server, state: b.text === server ? "saved" : "unsaved" } : b));
    } finally {
      inFlight.current = false;
    }
  }, [id]);
  const briefText = brief?.text ?? null;
  useEffect(() => {
    latestBrief.current = briefText;
    if (briefText === null || briefText === serverBrief.current) return;
    const timer = setTimeout(() => void flushBrief(), 1000);
    return () => clearTimeout(timer);
  }, [briefText, flushBrief]);
  // Al salir del proyecto con cambios sin guardar, se envían igualmente (en orden, tras la escritura en vuelo).
  useEffect(
    () => () => {
      if (latestBrief.current !== null && latestBrief.current !== serverBrief.current) void flushBrief();
    },
    [flushBrief],
  );

  if (missing) {
    return (
      <div className="px-4 py-8 md:px-8">
        <BackLink />
        <p className="mt-16 text-center text-fg-3">{p.notFound}</p>
      </div>
    );
  }
  if (!project) return <div className="shimmer m-8 h-60 rounded-2xl" />;
  const on = active?.id === project.id;

  async function addFolder() {
    const name = newFolder?.trim();
    if (!name || !project) return;
    try {
      const f = await studio.createFolder(project.id, name);
      setProject({ ...project, folders: [...project.folders, f].sort((a, b) => a.name.localeCompare(b.name)) });
      setNewFolder(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function renameFolder(fid: string, current: string) {
    const name = window.prompt(p.folders.rename, current)?.trim();
    if (!name || !project) return;
    const f = await studio.renameFolder(fid, name).catch((e) => setError(String(e)));
    if (f) setProject({ ...project, folders: project.folders.map((x) => (x.id === fid ? f : x)) });
  }

  async function removeFolder(fid: string, name: string) {
    if (!project || !window.confirm(p.folders.confirmDelete(name))) return;
    await studio.deleteFolder(fid).catch((e) => setError(String(e)));
    setProject({ ...project, folders: project.folders.filter((x) => x.id !== fid) });
    if (folder === fid) setFolder(undefined);
  }

  return (
    <div className="px-4 py-6 pb-28 md:px-8">
      <BackLink />
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <ProjectCover project={project} className="hidden w-40 shrink-0 sm:block" />
        <div className="min-w-0 flex-1">
          <h1 className="headline truncate text-[34px] md:text-[48px]">{project.name}</h1>
          {project.description && <p className="mt-1 text-fg-3">{project.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/supercomputer"
            onClick={() => setActiveProject({ id: project.id, name: project.name })}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-surface-4 px-3 text-sm text-fg-2 hover:text-fg"
          >
            <MessageSquare className="size-4" /> {p.chat}
          </Link>
          <button
            type="button"
            onClick={() => setActiveProject(on ? null : { id: project.id, name: project.name })}
            className={clsx("flex h-9 items-center gap-1.5 rounded-xl px-3.5 text-sm font-semibold", on ? "bg-surface-4 text-fg-2" : "bg-lime text-ink")}
          >
            {on && <Check className="size-4" />}
            {on ? p.deactivate : p.activate}
          </button>
        </div>
      </div>
      {!on && <p className="mt-2 text-xs text-fg-3">{p.activeHint}</p>}

      <nav className="mt-6 flex gap-1 border-b border-line">
        {(["assets", "brief", "settings"] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={clsx("-mb-px border-b-2 px-3 pb-2.5 text-[15px] font-medium", tab === k ? "border-fg text-fg" : "border-transparent text-fg-3 hover:text-fg-2")}
          >
            {p.tabs[k]}
          </button>
        ))}
      </nav>
      {error && <p className="mt-4 rounded-2xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {tab === "assets" && (
        <div className="mt-5 flex flex-col gap-5 lg:flex-row">
          <aside className="w-full shrink-0 lg:w-56">
            <p className="mb-2 px-2 text-xs font-semibold tracking-wide text-fg-4 uppercase">{p.folders.title}</p>
            <ul className="flex flex-wrap gap-1 lg:flex-col">
              <FolderButton active={folder === undefined} onClick={() => setFolder(undefined)} label={p.folders.all} />
              <FolderButton active={folder === "none"} onClick={() => setFolder("none")} label={p.folders.unfiled} />
              {project.folders.map((f) => (
                <li key={f.id} className="group flex items-center">
                  <FolderButton active={folder === f.id} onClick={() => setFolder(f.id)} label={f.name} bare />
                  <button type="button" title={p.folders.rename} onClick={() => renameFolder(f.id, f.name)} className="hidden p-1 text-fg-4 group-hover:block hover:text-fg">
                    <Pencil className="size-3.5" />
                  </button>
                  <button type="button" title={p.folders.delete} onClick={() => removeFolder(f.id, f.name)} className="hidden p-1 text-fg-4 group-hover:block hover:text-danger">
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              ))}
            </ul>
            {newFolder === null ? (
              <button type="button" onClick={() => setNewFolder("")} className="mt-2 flex items-center gap-1.5 px-2 text-sm text-fg-3 hover:text-fg">
                <FolderPlus className="size-4" /> {p.folders.add}
              </button>
            ) : (
              <form
                className="mt-2 flex gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  void addFolder();
                }}
              >
                <input
                  autoFocus
                  value={newFolder}
                  onChange={(e) => setNewFolder(e.target.value)}
                  onKeyDown={(e) => e.key === "Escape" && setNewFolder(null)}
                  maxLength={80}
                  placeholder={p.folders.placeholder}
                  className="h-8 min-w-0 flex-1 rounded-lg border border-line-2 bg-surface-3 px-2 text-sm outline-none focus:border-lime/60"
                />
                <button type="submit" className="rounded-lg bg-lime px-2 text-ink">
                  <Check className="size-4" />
                </button>
              </form>
            )}
          </aside>
          <div className="min-w-0 flex-1">
            <Assets project={project} folder={folder} onCover={(cover) => setProject({ ...project, cover })} />
          </div>
        </div>
      )}
      {tab === "brief" && brief && (
        <BriefEditor
          draft={brief}
          onChange={(text) => setBrief((b) => (b ? { ...b, text, state: text === b.saved ? "saved" : "unsaved" } : b))}
          onRetry={() => void flushBrief()}
        />
      )}
      {tab === "settings" && (
        <Settings
          project={project}
          onSaved={setProject}
          onDeleted={() => {
            if (on) setActiveProject(null);
            router.push("/projects");
          }}
        />
      )}
    </div>
  );
}

function BackLink() {
  const { t } = useI18n();
  return (
    <Link href="/projects" className="inline-flex items-center gap-1.5 text-sm text-fg-3 hover:text-fg">
      <ArrowLeft className="size-4" /> {t.projects.back}
    </Link>
  );
}

function FolderButton({ active, onClick, label, bare }: { active: boolean; onClick: () => void; label: string; bare?: boolean }) {
  const button = (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left text-sm transition-colors",
        active ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg-2",
      )}
    >
      <Folder className="size-4 shrink-0" />
      <span className="truncate">{label}</span>
    </button>
  );
  return bare ? button : <li className="flex">{button}</li>;
}

/** Generaciones del proyecto (o de una carpeta), con selección para moverlas o usar una como portada. */
function Assets({ project, folder, onCover }: { project: Project; folder?: string; onCover: (cover: string | null) => void }) {
  const { t } = useI18n();
  const p = t.projects;
  const h = t.history;
  const router = useRouter();
  const { items, loading, remove, setFavorite } = useGenerations({ project: project.id, folder });
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  const [others, setOthers] = useState<ProjectSummary[]>([]);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  // Movidas aquí: desaparecen de la vista al momento (el sondeo lo confirma después).
  const [gone, setGone] = useState<Set<string>>(new Set());
  useEffect(() => {
    studio.models().then((r) => setModels(modelMap(r.models))).catch(() => undefined);
    studio.projects().then((r) => setOthers(r.projects.filter((x) => x.id !== project.id))).catch(() => undefined);
  }, [project.id]);

  const shown = useMemo(() => items.filter((g) => !gone.has(g.id)), [items, gone]);
  const chosen = shown.filter((g) => picked.has(g.id));

  async function move(target: string) {
    if (!chosen.length || !target) return;
    const [kind, value] = target.split(":");
    const ids = chosen.map((g) => g.id);
    try {
      const res =
        kind === "folder"
          ? await studio.move(ids, project.id, value === "none" ? null : value)
          : await studio.move(ids, value === "none" ? null : value, null);
      // Sale de la vista lo que ya no corresponde a este proyecto o a la carpeta filtrada.
      const leaves = kind === "project" || (folder !== undefined && folder !== value);
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
      <div className="mb-3 flex justify-end">
        <button
          type="button"
          onClick={() => {
            setSelecting(!selecting);
            setPicked(new Set());
            setNotice(null);
          }}
          className={clsx("h-9 rounded-xl px-4 text-sm font-medium", selecting ? "bg-lime text-ink" : "bg-surface-3 text-fg-2 hover:text-fg")}
        >
          {selecting ? h.done : h.select}
        </button>
      </div>
      {shown.length === 0 ? (
        <p className="mt-12 text-center text-fg-3">{p.nothing}</p>
      ) : (
        <Masonry
          items={shown}
          itemKey={(g) => g.id}
          maxColumns={4}
          minColumnWidth={240}
          gap={16}
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
          {notice && <p className="w-full px-2 text-xs text-fg-3">{notice}</p>}
        </div>
      )}
    </>
  );
}

type BriefDraft = { text: string; saved: string; state: "saved" | "saving" | "unsaved" };

/** Brief en Markdown: el borrador vive en ProjectView, que lo guarda solo. */
function BriefEditor({ draft, onChange, onRetry }: { draft: BriefDraft; onChange: (text: string) => void; onRetry: () => void }) {
  const { t } = useI18n();
  const b = t.projects.brief;
  const [preview, setPreview] = useState(false);
  return (
    <div className="mt-5 max-w-4xl">
      <div className="mb-2 flex items-center gap-3 text-xs text-fg-3">
        <span>{b.hint}</span>
        {draft.state === "unsaved" ? (
          <button type="button" onClick={onRetry} className="ml-auto text-warning hover:underline">
            {b.unsaved} · {b.retry}
          </button>
        ) : (
          <span className="ml-auto">{b[draft.state]}</span>
        )}
        <button type="button" onClick={() => setPreview(!preview)} className="rounded-lg bg-surface-4 px-2.5 py-1 font-medium text-fg-2 hover:text-fg">
          {preview ? <Pencil className="size-3.5" /> : "Markdown"}
        </button>
      </div>
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

function Settings({ project, onSaved, onDeleted }: { project: Project; onSaved: (p: Project) => void; onDeleted: () => void }) {
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
    <div className="mt-5 max-w-2xl space-y-4">
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
        <ProjectCover project={project} className="w-72" />
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
