"use client";

import clsx from "clsx";
import { CircleHelp, Clapperboard, Info, Loader2, Palette, Trash2, Upload, Volume2, VolumeX, Waves } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Masonry } from "@/components/masonry";
import { studio, type KatanaCategory, type KatanaPreset, type KatanaProject } from "@/lib/studio";
import { HowItWorks } from "./how-it-works";
import { PublishModal } from "./publish-modal";
import { RecreateModal } from "./recreate-modal";

type Tab = "all" | "mine" | string;

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  motion_transfer: <Waves className="size-4" />,
  style_transfer: <Palette className="size-4" />,
  personalized_edits: <Clapperboard className="size-4" />,
};
// Orden de las pestañas en higgsfield.ai/katana.
const TAB_ORDER = ["motion_transfer", "style_transfer", "personalized_edits"];

/** Reproduce el video solo mientras se ve (la galería tiene decenas de videos). */
function useInView<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, seen] as const;
}

function LazyVideo({ src, poster, muted = true, className }: { src: string; poster?: string; muted?: boolean; className?: string }) {
  const [ref, seen] = useInView<HTMLVideoElement>();
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (seen) void v.play().catch(() => {});
    else v.pause();
  }, [seen, ref]);
  return <video ref={ref} src={seen ? src : undefined} poster={poster} muted={muted} loop playsInline preload="none" className={className} />;
}

/** Katana como en higgsfield.ai/katana: portada, galería de la comunidad por categorías y «Recrear plantilla». */
export function KatanaStudio() {
  const { t, locale } = useI18n();
  const k = t.katana;
  const [categories, setCategories] = useState<KatanaCategory[]>([]);
  const [presets, setPresets] = useState<KatanaPreset[] | null>(null);
  const [projects, setProjects] = useState<KatanaProject[]>([]);
  const [tab, setTab] = useState<Tab>("all");
  const [recreate, setRecreate] = useState<{ preset?: KatanaPreset; project?: KatanaProject } | null>(null);
  const [how, setHow] = useState(false);
  const [publish, setPublish] = useState(false);
  const [error, setError] = useState("");
  const wall = useRef<HTMLDivElement>(null);

  useEffect(() => {
    studio.katanaPresets(locale === "en" ? "en" : "es").then(
      (r) => {
        setCategories(r.categories ?? []);
        setPresets(r.presets);
      },
      (e) => {
        setPresets([]);
        setError(e instanceof Error ? e.message : String(e));
      },
    );
  }, [locale]);
  useEffect(() => {
    studio.katanaProjects().then((r) => setProjects(r.projects)).catch(() => {});
  }, []);

  const upsert = (p: KatanaProject) => setProjects((list) => [p, ...list.filter((x) => x.id !== p.id)]);

  async function openProject(id: string) {
    setError("");
    try {
      setRecreate({ project: await studio.katanaProject(id) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(id: string) {
    await studio.katanaDelete(id).catch(() => {});
    setProjects((list) => list.filter((x) => x.id !== id));
  }

  const list = presets ?? [];
  const shown = tab === "all" ? list : list.filter((p) => p.category === tab);
  const tabs = [...categories].sort((a, b) => TAB_ORDER.indexOf(a.id) - TAB_ORDER.indexOf(b.id));
  const side = list.filter((p) => p.thumbnail_url);

  return (
    <div className="min-h-screen w-full bg-black">
      {/* Portada */}
      <section className="relative isolate flex flex-col items-center justify-center gap-6 overflow-hidden px-4 pb-10 pt-16 md:min-h-[520px] md:pt-10">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 hidden md:block">
          {side.slice(0, 2).map((p, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={p.id} src={p.thumbnail_url} alt="" className="absolute top-1/2 h-[300px] w-[230px] -translate-y-1/2 object-cover opacity-90"
              style={{ left: i ? "8%" : "-2%", clipPath: "polygon(0 18%, 100% 0, 100% 100%, 0 82%)", filter: i ? "none" : "brightness(.5)" }} />
          ))}
          {side.slice(2, 4).map((p, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={p.id} src={p.thumbnail_url} alt="" className="absolute top-1/2 h-[300px] w-[230px] -translate-y-1/2 object-cover opacity-90"
              style={{ right: i ? "-2%" : "8%", clipPath: "polygon(0 0, 100% 18%, 100% 82%, 0 100%)", filter: i ? "brightness(.5)" : "none" }} />
          ))}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(0,0,0,.2),rgba(0,0,0,.95)_70%)]" />
        </div>
        <h1 className="select-none text-center text-[72px] font-black italic leading-none tracking-tight md:text-[132px]"
          style={{ background: "linear-gradient(180deg,#fff 0%,#d9d9d9 38%,#6b6b6b 52%,#e6e6e6 70%,#9a9a9a 100%)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent", transform: "skewX(-8deg)" }}>
          KATANA
        </h1>
        <p className="max-w-xl text-center text-lg text-fg-2">{k.tagline}</p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <button type="button" onClick={() => setRecreate({})}
            className="h-14 rounded-2xl bg-lime px-7 text-lg font-semibold text-black shadow-[0_5px_0_#8ead10] transition hover:bg-lime-400 active:translate-y-0.5 active:shadow-[0_3px_0_#8ead10]">
            {k.start}
          </button>
          <button type="button" onClick={() => setHow(true)} className="flex h-14 items-center gap-2 px-3 text-lg font-semibold hover:text-lime">
            <CircleHelp className="size-6" />
            {k.how}
          </button>
        </div>
      </section>

      {/* Pestañas */}
      <div className="flex flex-wrap items-center gap-1 px-4 pb-6 md:px-6">
        <TabButton active={tab === "all"} onClick={() => setTab("all")}>{k.tabAll}</TabButton>
        {tabs.map((c) => (
          <TabButton key={c.id} active={tab === c.id} onClick={() => setTab(c.id)} icon={CATEGORY_ICON[c.id]}>
            {k.categories[c.id] ?? c.name}
          </TabButton>
        ))}
        <TabButton active={tab === "mine"} onClick={() => setTab("mine")}>{k.tabMine}{projects.length ? ` · ${projects.length}` : ""}</TabButton>
        <button type="button" onClick={() => setPublish(true)}
          className="ml-auto flex h-11 shrink-0 items-center gap-2 rounded-full bg-surface-3 px-5 text-[15px] font-semibold hover:bg-surface-4">
          <Upload className="size-4" />
          {k.publish}
        </button>
      </div>

      {error && <p className="mx-4 mb-4 rounded-2xl border border-danger/50 bg-danger/10 p-3 text-sm text-danger md:mx-6">{error}</p>}

      {/* Muro */}
      <div ref={wall} className="px-4 pb-16 md:px-6">
        {tab === "mine" ? (
          projects.length ? (
            <Masonry items={projects} itemKey={(p) => p.id} maxColumns={3} minColumnWidth={280} gap={24}
              render={(p) => <ProjectCard project={p} onOpen={() => openProject(p.id)} onRemove={() => remove(p.id)} />} />
          ) : (
            <p className="py-16 text-center text-fg-3">{k.emptyMine}</p>
          )
        ) : presets === null ? (
          <p className="flex items-center justify-center gap-2 py-16 text-fg-3"><Loader2 className="size-5 animate-spin" />{k.loading}</p>
        ) : (
          <Masonry items={shown} itemKey={(p) => p.id} maxColumns={3} minColumnWidth={280} gap={24}
            render={(p) => <PresetCard preset={p} onRecreate={() => setRecreate({ preset: p })} />} />
        )}
      </div>

      {recreate && (
        <RecreateModal presets={list} preset={recreate.preset} project={recreate.project}
          onClose={() => setRecreate(null)} onProject={upsert} />
      )}
      {how && (
        <HowItWorks presets={list} onClose={() => setHow(false)}
          onExplore={() => { setHow(false); wall.current?.scrollIntoView({ behavior: "smooth" }); }} />
      )}
      {publish && <PublishModal onClose={() => setPublish(false)} onSaved={(p) => { upsert(p); setTab("mine"); }} />}
    </div>
  );
}

function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={clsx("flex h-11 shrink-0 items-center gap-2 rounded-full px-4 text-[15px] font-medium transition",
        active ? "bg-white text-black" : "text-fg-2 hover:bg-white/5")}>
      {icon}
      {children}
    </button>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={(e) => { e.stopPropagation(); onClick(); }}
      className="flex size-10 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur hover:bg-black/60">
      {children}
    </button>
  );
}

function PresetCard({ preset, onRecreate }: { preset: KatanaPreset; onRecreate: () => void }) {
  const { t } = useI18n();
  const k = t.katana;
  const [muted, setMuted] = useState(true);
  const [info, setInfo] = useState(false);
  const corner = preset.result_thumbnail_url || preset.person_url;
  return (
    <div role="button" tabIndex={0} onClick={onRecreate} onKeyDown={(e) => e.key === "Enter" && onRecreate()}
      className="group relative cursor-pointer overflow-hidden rounded-3xl border border-white/10 bg-surface-2"
      onMouseLeave={() => setInfo(false)}>
      <LazyVideo src={preset.video_url} poster={preset.thumbnail_url || undefined} muted={muted} className="block w-full" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-black/60 to-transparent" />
      <div className="absolute right-4 top-4 flex flex-col gap-3 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <IconButton label={k.info} onClick={() => setInfo((v) => !v)}><Info className="size-5" /></IconButton>
        <IconButton label={muted ? k.unmute : k.mute} onClick={() => setMuted((v) => !v)}>
          {muted ? <VolumeX className="size-5" /> : <Volume2 className="size-5" />}
        </IconButton>
      </div>
      {info && (
        <div onClick={(e) => e.stopPropagation()} className="absolute right-16 top-4 w-64 cursor-default rounded-2xl bg-surface-2/95 p-4 text-sm shadow-xl backdrop-blur">
          <p className="font-semibold">{preset.name}</p>
          {preset.description && <p className="mt-1 text-fg-2">{preset.description}</p>}
          <p className="mt-2 text-xs text-fg-3">{k.inspired}</p>
        </div>
      )}
      <div className="absolute inset-x-4 bottom-4 flex items-end justify-between gap-3">
        {preset.author ? (
          <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-white drop-shadow">
            {preset.author_avatar && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preset.author_avatar} alt="" className="size-6 rounded-full object-cover" />
            )}
            <span className="truncate">{k.by(preset.author)}</span>
          </span>
        ) : <span />}
        {corner && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={corner} alt="" className="h-24 w-[68px] shrink-0 rounded-xl border-2 border-white object-cover shadow-lg" />
        )}
      </div>
      <div className="absolute inset-x-4 bottom-4 translate-y-2 opacity-0 transition group-focus-within:translate-y-0 group-focus-within:opacity-100 group-hover:translate-y-0 group-hover:opacity-100">
        <span className="flex h-14 w-full items-center justify-center rounded-xl bg-white text-lg font-semibold text-black">{k.recreate}</span>
      </div>
    </div>
  );
}

function ProjectCard({ project, onOpen, onRemove }: { project: KatanaProject; onOpen: () => void; onRemove: () => void }) {
  const { t } = useI18n();
  const k = t.katana;
  return (
    <div role="button" tabIndex={0} onClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()}
      className="group relative cursor-pointer overflow-hidden rounded-3xl border border-white/10 bg-surface-2">
      <LazyVideo src={project.reference_url} className="block w-full" />
      <div className="absolute right-4 top-4 opacity-0 transition group-hover:opacity-100">
        <IconButton label={k.remove} onClick={onRemove}><Trash2 className="size-5" /></IconButton>
      </div>
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent p-4 pt-10">
        <p className="truncate font-semibold">{project.title}</p>
        <p className="text-xs text-fg-2">
          {new Date(project.updated_at).toLocaleDateString()} · {project.planned ? k.planned : k.notPlanned}
        </p>
      </div>
      <div className="absolute inset-x-4 bottom-4 translate-y-2 opacity-0 transition group-hover:translate-y-0 group-hover:opacity-100">
        <span className="flex h-14 w-full items-center justify-center rounded-xl bg-white text-lg font-semibold text-black">{k.recreate}</span>
      </div>
    </div>
  );
}
