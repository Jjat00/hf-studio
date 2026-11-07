"use client";

import clsx from "clsx";
import { ArrowDownAZ, AtSign, ChevronRight, Clock, FolderOpen, FolderPlus, Heart, Home, Layers, Loader2, Plus, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ElementLibrary } from "@/components/elements/element-library";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { ProjectCover } from "@/components/projects/project-parts";
import { setActiveProject, useActiveProject } from "@/lib/project";
import { outputSrc, studio } from "@/lib/studio";
import type { Generation, ProjectSummary } from "@/lib/types";
import { Composer } from "./composer";
import { CinemaShell, GenerationsGrid, SideItem, SidebarBrand } from "./shell";

type View = "home" | "generations" | "elements" | "favorites" | "projects";
const VIEWS: View[] = ["home", "generations", "elements", "favorites", "projects"];
/** Generaciones hechas con los modelos del compositor de Cinema Studio. */
const isCinemaModel = (model: string) => model.startsWith("higgsfield/cinema-studio/") || model === "higgsfield-ai/soul/cinema";

/** Cinema Studio (inicio): barra lateral con secciones y proyectos, el título, el compositor y «Mis proyectos». */
export function CinemaHome() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const view = (VIEWS.find((v) => v === params.get("v")) ?? "home") as View;
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    studio.projects().then(
      (r) => setProjects(r.projects),
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setProjects([]);
      },
    );
  }, []);

  const go = (v: View) => router.replace(v === "home" ? pathname : `${pathname}?v=${v}`, { scroll: false });

  async function createProject(name: string) {
    const made = await studio.createProject(name);
    setActiveProject({ id: made.id, name: made.name });
    router.push(`/cinema/${made.id}`);
  }

  return (
    <CinemaShell
      sidebar={(close) => (
        <HomeSidebar
          view={view}
          projects={projects}
          onView={(v) => {
            go(v);
            close();
          }}
          onCreate={createProject}
        />
      )}
    >
      {(menuButton) => (
        <div className="thin-scrollbar min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          <div className="sticky top-0 z-20 flex items-center gap-2 px-3 pt-3 md:hidden">{menuButton}</div>
          {error && <p className="mx-4 mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
          {view === "home" && <HomeView projects={projects} onCreate={createProject} onAll={() => go("projects")} onGenerations={() => go("generations")} />}
          {view === "generations" && <MyGenerations />}
          {view === "favorites" && <MyGenerations favorites />}
          {view === "elements" && <ElementLibrary />}
          {view === "projects" && <AllProjects projects={projects} onCreate={createProject} />}
        </div>
      )}
    </CinemaShell>
  );
}

function HomeSidebar({
  view,
  projects,
  onView,
  onCreate,
}: {
  view: View;
  projects: ProjectSummary[] | null;
  onView: (v: View) => void;
  onCreate: (name: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const active = useActiveProject();
  const [query, setQuery] = useState<string | null>(null);
  const [byName, setByName] = useState(false);
  const shown = useMemo(() => {
    const list = (projects ?? []).filter((p) => !query || p.name.toLowerCase().includes(query.toLowerCase()));
    return byName ? [...list].sort((a, b) => a.name.localeCompare(b.name)) : list;
  }, [projects, query, byName]);

  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      <SidebarBrand />
      <nav className="space-y-0.5">
        <SideItem icon={<Home className="size-4" />} label={cs.home} active={view === "home"} onClick={() => onView("home")} />
        <SideItem icon={<Sparkles className="size-4" />} label={cs.myGenerations} active={view === "generations"} onClick={() => onView("generations")} />
        <SideItem icon={<AtSign className="size-4" />} label={cs.myElements} active={view === "elements"} onClick={() => onView("elements")} />
        <SideItem icon={<Heart className="size-4" />} label={cs.myFavorites} active={view === "favorites"} onClick={() => onView("favorites")} />
      </nav>

      <div className="mt-6 flex items-center gap-1 px-2 pb-1">
        <p className="flex-1 text-[13px] font-medium text-fg-3">{cs.projects}</p>
        <button
          type="button"
          title={cs.searchProjects}
          aria-label={cs.searchProjects}
          onClick={() => setQuery((q) => (q === null ? "" : null))}
          className={clsx("rounded-md p-1 hover:text-fg", query !== null ? "text-fg" : "text-fg-3")}
        >
          <Search className="size-4" />
        </button>
        <button
          type="button"
          title={byName ? cs.sortRecent : cs.sortName}
          aria-label={byName ? cs.sortRecent : cs.sortName}
          onClick={() => setByName((b) => !b)}
          className={clsx("rounded-md p-1 hover:text-fg", byName ? "text-fg" : "text-fg-3")}
        >
          {byName ? <ArrowDownAZ className="size-4" /> : <Clock className="size-4" />}
        </button>
      </div>
      {query !== null && (
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={cs.searchProjects}
          className="mx-1 mb-1 h-8 rounded-lg border border-line-2 bg-surface-3 px-2 text-sm outline-none focus:border-lime/60"
        />
      )}
      <NewProjectButton onCreate={onCreate} />
      <div className="thin-scrollbar min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        {projects === null ? (
          <Loader2 className="m-3 size-4 animate-spin text-fg-3" />
        ) : (
          shown.map((p) => (
            <SideItem
              key={p.id}
              small
              href={`/cinema/${p.id}`}
              icon={<FolderOpen className="size-3.5" />}
              label={p.name}
              trailing={active?.id === p.id ? <span className="size-1.5 shrink-0 rounded-full bg-lime" /> : undefined}
            />
          ))
        )}
      </div>
      <div className="mt-2 border-t border-line pt-2">
        <SideItem
          icon={<Layers className="size-4" />}
          label={cs.allProjects}
          active={view === "projects"}
          onClick={() => onView("projects")}
          trailing={<ChevronRight className="size-4 text-fg-3" />}
        />
      </div>
    </div>
  );
}

/** «Nuevo proyecto»: pide el nombre ahí mismo y abre el proyecto creado. */
function NewProjectButton({ onCreate, tile }: { onCreate: (name: string) => Promise<void>; tile?: boolean }) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!name?.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(name.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  if (name === null) {
    return tile ? (
      <button
        type="button"
        onClick={() => setName("")}
        className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-surface-2 text-sm font-medium text-fg-2 transition-colors hover:border-line-2 hover:text-fg"
      >
        <span className="flex size-12 items-center justify-center rounded-full bg-surface-4">
          <FolderPlus className="size-5" />
        </span>
        {cs.newProject}
      </button>
    ) : (
      <SideItem small icon={<Plus className="size-3.5" />} label={cs.newProject} onClick={() => setName("")} />
    );
  }
  return (
    <form
      className={clsx("flex flex-col gap-2", tile ? "aspect-video justify-center rounded-2xl border border-line-2 bg-surface-2 p-4" : "mx-1 mb-1")}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && setName(null)}
        maxLength={120}
        placeholder={cs.newProjectName}
        className="h-9 rounded-lg border border-line-2 bg-surface-3 px-2.5 text-sm outline-none focus:border-lime/60"
      />
      <div className="flex gap-1.5">
        <button type="submit" disabled={!name.trim() || busy} className="flex h-8 flex-1 items-center justify-center gap-1.5 rounded-lg bg-lime text-sm font-semibold text-ink disabled:opacity-40">
          {busy && <Loader2 className="size-3.5 animate-spin" />}
          {cs.create}
        </button>
        <button type="button" onClick={() => setName(null)} className="h-8 rounded-lg bg-surface-4 px-3 text-sm text-fg-2 hover:text-fg">
          {cs.cancel}
        </button>
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </form>
  );
}

function ProjectGrid({ projects, onCreate, limit }: { projects: ProjectSummary[] | null; onCreate: (name: string) => Promise<void>; limit?: number }) {
  const { t } = useI18n();
  const active = useActiveProject();
  if (projects === null) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="shimmer aspect-video rounded-2xl" />
        ))}
      </div>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <li>
        <NewProjectButton tile onCreate={onCreate} />
      </li>
      {(limit ? projects.slice(0, limit) : projects).map((p) => (
        <li key={p.id}>
          <Link href={`/cinema/${p.id}`} className="group block">
            <ProjectCover project={p} className={clsx("rounded-2xl transition group-hover:brightness-110", active?.id === p.id && "ring-2 ring-lime/60")} />
            <p className="mt-2 truncate px-1 text-[15px] font-semibold text-fg">{p.name}</p>
            <p className="truncate px-1 text-xs text-fg-3">{p.description || t.projects.generations(p.generations)}</p>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function HomeView({
  projects,
  onCreate,
  onAll,
  onGenerations,
}: {
  projects: ProjectSummary[] | null;
  onCreate: (name: string) => Promise<void>;
  onAll: () => void;
  onGenerations: () => void;
}) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  // Lo que se lanza desde aquí aparece al momento (con su carga) y se actualiza solo hasta tener el resultado.
  const generations = useGenerations();
  const latest = generations.items.slice(0, 8);
  const [recent, setRecent] = useState<Generation[]>([]);
  useEffect(() => {
    studio
      .list(30)
      .then((r) => setRecent(r.generations.filter((g) => g.status === "completed" && ["image", "video"].includes(g.outputs[0]?.kind ?? "")).slice(0, 3)))
      .catch(() => undefined);
  }, []);
  // Abanico como el carrusel de Higgsfield: la del medio, delante y más grande.
  const fan = recent.length === 3 ? [recent[1], recent[0], recent[2]] : recent;

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col items-center px-4 pt-8 pb-16 md:pt-14">
      {fan.length > 0 && (
        <div className="mb-8 flex items-center justify-center">
          {fan.map((g, i) => {
            const center = fan.length === 3 ? i === 1 : i === 0;
            const out = g.outputs[0];
            return (
              <div
                key={g.id}
                className={clsx(
                  "overflow-hidden rounded-2xl border border-line-2 bg-surface-3 shadow-2xl",
                  center ? "z-10 h-32 w-56 sm:h-40 sm:w-72" : "hidden h-24 w-40 opacity-80 sm:block sm:h-28 sm:w-44",
                  !center && (i === 0 ? "-mr-6" : "-ml-6"),
                )}
              >
                {out.kind === "video" ? (
                  <video src={outputSrc(out)} muted playsInline autoPlay loop className="size-full object-cover" />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={outputSrc(out)} alt="" className="size-full object-cover" />
                )}
              </div>
            );
          })}
        </div>
      )}
      <h1 className="headline bg-gradient-to-b from-white to-white/55 bg-clip-text text-center text-[34px] leading-none text-transparent uppercase sm:text-[52px]">{cs.hero}</h1>
      <div className="mt-8 w-full max-w-[880px]">
        <Composer panelsBelow onGenerated={generations.add} />
      </div>
      {(generations.loading || generations.error || latest.length > 0) && (
        <div className="mt-12 w-full">
          <button type="button" onClick={onGenerations} className="mb-4 flex items-center gap-1 text-[18px] font-semibold text-fg hover:text-lime">
            {cs.recent} <ChevronRight className="size-5" />
          </button>
          {generations.error && <p className="mb-3 rounded-xl bg-danger/10 p-3 text-sm text-danger">{generations.error}</p>}
          {(generations.loading || latest.length > 0) && <GenerationsGrid list={generations} items={latest} empty={cs.noGenerations} />}
        </div>
      )}
      <div className="mt-16 w-full">
        <button type="button" onClick={onAll} className="mb-4 flex items-center gap-1 text-[18px] font-semibold text-fg hover:text-lime">
          {cs.myProjects} <ChevronRight className="size-5" />
        </button>
        <ProjectGrid projects={projects} onCreate={onCreate} limit={5} />
        {projects?.length === 0 && <p className="mt-4 text-sm text-fg-3">{cs.noProjects}</p>}
      </div>
    </div>
  );
}

function AllProjects({ projects, onCreate }: { projects: ProjectSummary[] | null; onCreate: (name: string) => Promise<void> }) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const [query, setQuery] = useState("");
  const shown = projects?.filter((p) => !query || p.name.toLowerCase().includes(query.toLowerCase())) ?? null;
  return (
    <div className="px-4 py-6 md:px-8">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="headline flex-1 text-[34px] md:text-[44px]">{cs.allProjects}</h1>
        <label className="flex h-9 w-full items-center gap-2 rounded-lg border border-line-2 bg-surface-2 px-2.5 sm:w-64">
          <Search className="size-4 text-fg-3" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={cs.searchProjects} className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </label>
      </div>
      <ProjectGrid projects={shown} onCreate={onCreate} />
    </div>
  );
}

function MyGenerations({ favorites }: { favorites?: boolean }) {
  const { t } = useI18n();
  const cs = t.cinemaStudio;
  const list = useGenerations({ favorite: favorites });
  const [onlyCinema, setOnlyCinema] = useState(!favorites);
  const items = useMemo(() => (onlyCinema ? list.items.filter((g) => isCinemaModel(g.model)) : list.items), [list.items, onlyCinema]);
  return (
    <div className="px-4 py-6 md:px-8">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="headline flex-1 text-[34px] md:text-[44px]">{favorites ? cs.myFavorites : cs.myGenerations}</h1>
        <div className="flex rounded-lg bg-surface-3 p-0.5 text-sm font-medium">
          {[true, false].map((only) => (
            <button
              key={String(only)}
              type="button"
              onClick={() => setOnlyCinema(only)}
              className={clsx("rounded-md px-3 py-1.5", onlyCinema === only ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg")}
            >
              {only ? cs.onlyCinema : cs.everything}
            </button>
          ))}
        </div>
      </div>
      <GenerationsGrid list={list} items={items} empty={cs.noGenerations} />
      {list.hasMore && (
        <div className="mt-6 flex justify-center">
          <button type="button" onClick={list.loadMore} className="h-9 rounded-lg bg-surface-3 px-4 text-sm text-fg-2 hover:text-fg">
            {list.loadingMore ? <Loader2 className="size-4 animate-spin" /> : "…"}
          </button>
        </div>
      )}
    </div>
  );
}
