"use client";

import clsx from "clsx";
import {
  ArrowLeft,
  AtSign,
  Check,
  ChevronDown,
  Clapperboard,
  FileText,
  Folder,
  FolderOpen,
  LayoutGrid,
  ListFilter,
  Loader2,
  MessageSquare,
  MoreVertical,
  Pencil,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  Upload,
  Workflow,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ElementLibrary } from "@/components/elements/element-library";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { AssetGrid, BriefEditor, ProjectSettings, useBriefDraft } from "@/components/projects/project-parts";
import { setActiveProject, useActiveProject } from "@/lib/project";
import { studio } from "@/lib/studio";
import type { Generation, Project } from "@/lib/types";
import { Composer, type ComposerHandle } from "./composer";
import { DirectorPanel } from "./director";
import { CinemaShell, Dropdown, SideItem } from "./shell";

type View = "assets" | "brief" | "settings" | "elements";
const VIEWS: View[] = ["assets", "brief", "settings", "elements"];
type Filters = { type: "all" | "image" | "video"; model: string; status: "all" | "done" | "running" | "failed"; hideFailed: boolean; liked: boolean };
const NO_FILTERS: Filters = { type: "all", model: "", status: "all", hideFailed: false, liked: false };
const FAILED = new Set(["failed", "nsfw", "canceled", "timed_out"]);

/** Espacio de un proyecto en Cinema Studio: carpetas, assets, brief, ajustes, elementos, AI Director y el compositor. */
export function CinemaProject({ id }: { id: string }) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = (VIEWS.find((v) => v === params.get("view")) ?? "assets") as View;
  const active = useActiveProject();
  const [project, setProject] = useState<Project | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [folder, setFolder] = useState<string | undefined>(undefined);
  const [director, setDirector] = useState(params.get("director") === "1");
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [columns, setColumns] = useState(4);
  const [selecting, setSelecting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const composer = useRef<ComposerHandle>(null);
  const upload = useRef<HTMLInputElement>(null);
  const { brief, init, change, retry } = useBriefDraft(id, setProject);

  useEffect(() => {
    studio.project(id).then(
      (pr) => {
        setProject(pr);
        init(pr.brief);
        // Entrar en un proyecto lo deja como activo: lo que se genere en otros estudios también va aquí.
        setActiveProject({ id: pr.id, name: pr.name });
      },
      () => setMissing(true),
    );
  }, [id, init]);

  const list = useGenerations({ project: id, folder });
  const shownList = useMemo(() => {
    const items = list.items.filter((g) => {
      if (filters.model && g.model !== filters.model) return false;
      if (filters.liked && !g.favorite) return false;
      if (filters.hideFailed && FAILED.has(g.status)) return false;
      if (filters.status === "done" && g.status !== "completed") return false;
      if (filters.status === "running" && g.terminal) return false;
      if (filters.status === "failed" && !FAILED.has(g.status)) return false;
      return true;
    });
    return { ...list, items };
  }, [list, filters]);
  const modelsInProject = useMemo(() => [...new Set(list.items.map((g) => g.model))].sort(), [list.items]);
  const filtered = JSON.stringify(filters) !== JSON.stringify(NO_FILTERS);

  const go = (v: View) => router.replace(v === "assets" ? pathname : `${pathname}?view=${v}`, { scroll: false });

  if (missing) {
    return (
      <div className="flex flex-col items-center gap-4 px-4 py-20 text-center">
        <p className="text-fg-3">{t.projects.notFound}</p>
        <button type="button" onClick={() => router.push("/cinema")} className="h-9 rounded-lg bg-surface-3 px-4 text-sm text-fg-2 hover:text-fg">
          {cs.back}
        </button>
      </div>
    );
  }
  if (!project) return <div className="shimmer m-6 h-[60vh] rounded-2xl" />;

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      await composer.current?.addFiles(Array.from(files));
    } finally {
      setUploading(false);
      if (upload.current) upload.current.value = "";
    }
  }

  const title = view === "brief" ? cs.projectBrief : view === "settings" ? cs.settings : view === "elements" ? cs.elements : project.name;
  const realFolder = folder && folder !== "none" ? folder : null;

  return (
    <CinemaShell
      sidebar={(close) => (
        <ProjectSidebar
          project={project}
          view={view}
          folder={folder}
          director={director}
          onProject={setProject}
          onError={setError}
          onView={(v) => {
            go(v);
            close();
          }}
          onFolder={(f) => {
            setFolder(f);
            go("assets");
            close();
          }}
          onDirector={() => {
            setDirector((d) => !d);
            close();
          }}
        />
      )}
    >
      {(menuButton) => (
        <div className="flex min-h-0 flex-1">
          <div className="relative flex min-w-0 flex-1 flex-col">
            <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3 md:px-4">
              {menuButton}
              <h1 className="min-w-0 flex-1 truncate text-[16px] font-semibold">{title}</h1>
              {view === "brief" && brief && (
                <span className="hidden items-center gap-1.5 text-sm text-fg-3 sm:flex">
                  <span className={clsx("size-2 rounded-full", brief.state === "saved" ? "bg-success" : "bg-warning")} />
                  {t.projects.brief[brief.state]}
                </span>
              )}
              {view === "assets" && (
                <>
                  <Dropdown
                    label={cs.filter}
                    trigger={
                      <>
                        <ListFilter className="size-4" />
                        <span className="hidden sm:inline">{cs.filter}</span>
                        {filtered && <span className="size-1.5 rounded-full bg-lime" />}
                      </>
                    }
                    className="w-64"
                  >
                    {() => <FilterMenu filters={filters} setFilters={setFilters} models={modelsInProject} />}
                  </Dropdown>
                  <Dropdown
                    label={cs.view}
                    trigger={
                      <>
                        <LayoutGrid className="size-4" />
                        <span className="hidden sm:inline">{cs.view}</span>
                      </>
                    }
                  >
                    {() => (
                      <div className="p-2">
                        <p className="mb-2 flex justify-between text-xs font-semibold text-fg-3">
                          {cs.cardSize}
                          <span className="font-mono text-fg">{8 - columns}</span>
                        </p>
                        <input type="range" min={2} max={6} value={8 - columns} onChange={(e) => setColumns(8 - Number(e.target.value))} className="w-full" aria-label={cs.cardSize} />
                      </div>
                    )}
                  </Dropdown>
                  <input ref={upload} type="file" multiple hidden accept="image/*,video/*,audio/*" onChange={(e) => void onUpload(e.target.files)} />
                  <button
                    type="button"
                    onClick={() => upload.current?.click()}
                    disabled={uploading}
                    title={t.cinemaStudio.composer.addReferences}
                    className="flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm font-medium text-fg-2 hover:bg-surface-3 hover:text-fg disabled:opacity-50"
                  >
                    {uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
                    <span className="hidden sm:inline">{cs.upload}</span>
                  </button>
                </>
              )}
              {!director && (
                <button
                  type="button"
                  onClick={() => setDirector(true)}
                  className="flex h-9 items-center gap-1.5 rounded-lg bg-lime px-3 text-sm font-semibold text-ink hover:brightness-105"
                >
                  <Clapperboard className="size-4" />
                  <span className="hidden lg:inline">{cs.director}</span>
                </button>
              )}
            </header>
            {error && <p className="mx-4 mt-3 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

            {view === "assets" && (
              <>
                <div className="thin-scrollbar min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-3 pt-4 pb-72 md:px-4 md:pb-60">
                  <AssetGrid
                    project={project}
                    folder={folder}
                    list={shownList}
                    kind={filters.type}
                    columns={columns}
                    onCover={(cover) => setProject({ ...project, cover })}
                    onSelecting={setSelecting}
                    empty={
                      filtered && list.items.length > 0 ? (
                        <p className="mt-16 text-center text-fg-3">{cs.noMatches}</p>
                      ) : (
                        <div className="mt-[12vh] flex flex-col items-center gap-3 text-center">
                          <span className="flex size-14 items-center justify-center rounded-2xl border border-line-2 bg-surface-3 text-fg-2">
                            <Folder className="size-6" />
                          </span>
                          <p className="text-[19px] font-semibold text-fg">{cs.nothingTitle}</p>
                          <p className="text-fg-3">{cs.nothingHint}</p>
                        </div>
                      )
                    }
                  />
                </div>
                {!selecting && (
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 bg-gradient-to-t from-page via-page/80 to-transparent px-2 pt-10 pb-2 md:px-4 md:pb-4">
                    <div className="pointer-events-auto mx-auto max-w-[900px]">
                      <Composer ref={composer} projectId={project.id} folderId={realFolder} onGenerated={(g: Generation) => list.add(g)} />
                    </div>
                  </div>
                )}
              </>
            )}
            {view !== "assets" && (
              <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-6 md:px-10">
                {view === "brief" && brief && (
                  <div className="mx-auto max-w-4xl">
                    <h2 className="headline text-[34px] md:text-[40px]">{project.name}</h2>
                    <p className="mt-1 mb-5 text-sm text-fg-3">{new Date(project.updated_at).toLocaleString()}</p>
                    <BriefEditor draft={brief} onChange={change} onRetry={retry} template={t.projects.brief.template} />
                  </div>
                )}
                {view === "settings" && (
                  <div className="mx-auto max-w-2xl">
                    <ProjectSettings
                      key={project.updated_at}
                      project={project}
                      onSaved={(p) => {
                        setProject(p);
                        if (active?.id === p.id) setActiveProject({ id: p.id, name: p.name });
                      }}
                      onDeleted={() => {
                        if (active?.id === project.id) setActiveProject(null);
                        router.push("/cinema");
                      }}
                    />
                  </div>
                )}
                {view === "elements" && (
                  <div className="-mx-4 -my-6 md:-mx-10">
                    <ElementLibrary />
                  </div>
                )}
              </div>
            )}
          </div>

          {director && (
            <aside className="fixed inset-0 z-50 flex flex-col border-l border-line lg:static lg:z-auto lg:w-[420px] lg:shrink-0">
              <DirectorPanel projectId={project.id} onClose={() => setDirector(false)} />
            </aside>
          )}
        </div>
      )}
    </CinemaShell>
  );
}

function FilterMenu({ filters, setFilters, models }: { filters: Filters; setFilters: (f: Filters) => void; models: string[] }) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const set = (patch: Partial<Filters>) => setFilters({ ...filters, ...patch });
  const select = "h-8 w-full rounded-lg bg-surface-4 px-2 text-sm text-fg outline-none";
  return (
    <div className="space-y-2 p-2">
      <p className="text-[11px] font-semibold text-fg-4">{cs.type}</p>
      <select value={filters.type} onChange={(e) => set({ type: e.target.value as Filters["type"] })} className={select} aria-label={cs.type}>
        <option value="all">{cs.allTypes}</option>
        <option value="image">{cs.images}</option>
        <option value="video">{cs.videos}</option>
      </select>
      <select value={filters.model} onChange={(e) => set({ model: e.target.value })} className={select} aria-label={cs.allModels}>
        <option value="">{cs.allModels}</option>
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <select value={filters.status} onChange={(e) => set({ status: e.target.value as Filters["status"] })} className={select} aria-label={cs.status}>
        <option value="all">{cs.anyStatus}</option>
        <option value="done">{cs.statusDone}</option>
        <option value="running">{cs.statusRunning}</option>
        <option value="failed">{cs.statusFailed}</option>
      </select>
      <label className="flex items-center justify-between rounded-lg px-1 py-1 text-sm text-fg-2">
        {cs.hideFailed}
        <input type="checkbox" checked={filters.hideFailed} onChange={(e) => set({ hideFailed: e.target.checked })} />
      </label>
      <div className="border-t border-line pt-2">
        <p className="mb-1 text-[11px] font-semibold text-fg-4">{cs.activity}</p>
        {[false, true].map((liked) => (
          <button
            key={String(liked)}
            type="button"
            onClick={() => set({ liked })}
            className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm text-fg-2 hover:bg-surface-4 hover:text-fg"
          >
            {liked ? cs.activityLiked : cs.activityAll}
            {filters.liked === liked && <Check className="size-4 text-lime" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function ProjectSidebar({
  project,
  view,
  folder,
  director,
  onProject,
  onError,
  onView,
  onFolder,
  onDirector,
}: {
  project: Project;
  view: View;
  folder: string | undefined;
  director: boolean;
  onProject: (p: Project) => void;
  onError: (e: string | null) => void;
  onView: (v: View) => void;
  onFolder: (f: string | undefined) => void;
  onDirector: () => void;
}) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const p = t.projects;
  const router = useRouter();
  const [toolsOpen, setToolsOpen] = useState(true);
  const [query, setQuery] = useState<string | null>(null);
  const [newFolder, setNewFolder] = useState<string | null>(null);
  const folders = project.folders.filter((f) => !query || f.name.toLowerCase().includes(query.toLowerCase()));

  async function addFolder() {
    const name = newFolder?.trim();
    if (!name) return;
    try {
      const f = await studio.createFolder(project.id, name);
      onProject({ ...project, folders: [...project.folders, f].sort((a, b) => a.name.localeCompare(b.name)) });
      setNewFolder(null);
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  async function renameFolder(fid: string, current: string) {
    const name = window.prompt(p.folders.rename, current)?.trim();
    if (!name) return;
    const f = await studio.renameFolder(fid, name).catch((e) => onError(String(e)));
    if (f) onProject({ ...project, folders: project.folders.map((x) => (x.id === fid ? f : x)) });
  }

  async function removeFolder(fid: string, name: string) {
    if (!window.confirm(p.folders.confirmDelete(name))) return;
    await studio.deleteFolder(fid).catch((e) => onError(String(e)));
    onProject({ ...project, folders: project.folders.filter((x) => x.id !== fid) });
    if (folder === fid) onFolder(undefined);
  }

  async function removeProject() {
    if (!window.confirm(p.settings.confirmDelete(project.name))) return;
    try {
      await studio.deleteProject(project.id);
      setActiveProject(null);
      router.push("/cinema");
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="thin-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto p-3">
      <SideItem icon={<ArrowLeft className="size-4" />} label={cs.back} href="/cinema" />
      <div className="mt-2 mb-2 flex items-center gap-2 px-2">
        <FolderOpen className="size-5 shrink-0 text-fg-3" />
        <p className="min-w-0 flex-1 truncate text-[15px] font-semibold">{project.name}</p>
        <Dropdown
          label={cs.projectMenu}
          trigger={<MoreVertical className="size-4" />}
          buttonClassName="flex size-7 items-center justify-center rounded-md text-fg-3 hover:bg-surface-3 hover:text-fg"
          className="w-48"
        >
          {(close) => (
            <>
              <button
                type="button"
                onClick={() => {
                  close();
                  onView("settings");
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-fg-2 hover:bg-surface-4 hover:text-fg"
              >
                <Settings className="size-4" /> {cs.settings}
              </button>
              <button
                type="button"
                onClick={() => {
                  close();
                  void removeProject();
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-danger hover:bg-surface-4"
              >
                <Trash2 className="size-4" /> {cs.deleteProject}
              </button>
            </>
          )}
        </Dropdown>
      </div>
      <nav className="space-y-0.5">
        <SideItem icon={<FileText className="size-4" />} label={cs.projectBrief} active={view === "brief"} onClick={() => onView("brief")} />
        <SideItem icon={<Settings className="size-4" />} label={cs.settings} active={view === "settings"} onClick={() => onView("settings")} />
        <SideItem icon={<AtSign className="size-4" />} label={cs.elements} active={view === "elements"} onClick={() => onView("elements")} />
        <SideItem
          icon={<Sparkles className="size-4" />}
          label={cs.tools}
          onClick={() => setToolsOpen((o) => !o)}
          trailing={<ChevronDown className={clsx("size-4 text-fg-3 transition-transform", !toolsOpen && "-rotate-90")} />}
        />
        {toolsOpen && (
          <div className="space-y-0.5 pl-4">
            <SideItem small icon={<Workflow className="size-3.5" />} label={cs.canvas} href="/spaces" />
            <SideItem small icon={<MessageSquare className="size-3.5" />} label={cs.chat} href="/supercomputer" />
            <SideItem small icon={<Clapperboard className="size-3.5" />} label={cs.director} active={director} onClick={onDirector} />
          </div>
        )}
      </nav>

      <div className="mt-5 flex items-center gap-1 px-2 pb-1">
        <p className="flex-1 text-[13px] font-medium text-fg-3">{cs.folders}</p>
        <button
          type="button"
          title={cs.searchFolders}
          aria-label={cs.searchFolders}
          onClick={() => setQuery((q) => (q === null ? "" : null))}
          className={clsx("rounded-md p-1 hover:text-fg", query !== null ? "text-fg" : "text-fg-3")}
        >
          <Search className="size-4" />
        </button>
      </div>
      {query !== null && (
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={cs.searchFolders}
          className="mx-1 mb-1 h-8 rounded-lg border border-line-2 bg-surface-3 px-2 text-sm outline-none focus:border-lime/60"
        />
      )}
      <div className="space-y-0.5">
        <SideItem icon={<Sparkles className="size-4" />} label={cs.allAssets} active={view === "assets" && folder === undefined} onClick={() => onFolder(undefined)} />
        {newFolder === null ? (
          <SideItem small icon={<Plus className="size-3.5" />} label={cs.addFolder} onClick={() => setNewFolder("")} />
        ) : (
          <form
            className="mx-1 flex gap-1"
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
            <button type="submit" className="rounded-lg bg-lime px-2 text-ink" aria-label={cs.addFolder}>
              <Check className="size-4" />
            </button>
          </form>
        )}
        <SideItem small icon={<Folder className="size-3.5" />} label={cs.unfiled} active={view === "assets" && folder === "none"} onClick={() => onFolder("none")} />
        {folders.map((f) => (
          <div key={f.id} className="group relative">
            <SideItem small icon={<Folder className="size-3.5 text-sky-300" />} label={f.name} active={view === "assets" && folder === f.id} onClick={() => onFolder(f.id)} />
            <span className="absolute top-1/2 right-1 hidden -translate-y-1/2 gap-0.5 group-hover:flex">
              <button type="button" title={p.folders.rename} aria-label={p.folders.rename} onClick={() => void renameFolder(f.id, f.name)} className="rounded p-1 text-fg-4 hover:text-fg">
                <Pencil className="size-3.5" />
              </button>
              <button type="button" title={p.folders.delete} aria-label={p.folders.delete} onClick={() => void removeFolder(f.id, f.name)} className="rounded p-1 text-fg-4 hover:text-danger">
                <Trash2 className="size-3.5" />
              </button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
