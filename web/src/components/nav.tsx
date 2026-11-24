"use client";

import clsx from "clsx";
import { ChevronDown, ChevronRight, FolderOpen, Globe, LogOut, Menu, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import type { Dict } from "@/lib/i18n";
import { MEGA_MENUS, type MegaMenu, type MenuEntry } from "@/lib/menu";
import { setActiveProject, useActiveProject } from "@/lib/project";
import { Approvals } from "./generations/approvals";
import { useI18n } from "./i18n-provider";
import { Logo } from "./logo";

type Label = Exclude<keyof Dict["nav"], "status">;
type Item = {
  href: string;
  label: Label;
  badge?: "new" | "top";
  mega?: MegaMenu["key"];
  match: (p: string, q: URLSearchParams) => boolean;
};

const tabIs = (q: URLSearchParams, ...tabs: (string | null)[]) => tabs.includes(q.get("tab"));

/** Barra principal, en el orden de Higgsfield: secciones por medio (con menú) y luego los productos estrella. */
const PRIMARY: Item[] = [
  { href: "/", label: "explore", match: (p) => p === "/" },
  { href: "/image", label: "image", mega: "image", match: (p) => p.startsWith("/image") },
  { href: "/video", label: "video", mega: "video", match: (p, q) => p.startsWith("/video") && tabIs(q, null, "create", "edit", "motion") },
  { href: "/audio", label: "audio", mega: "audio", match: (p) => ["/audio", "/voice", "/voices", "/sounds"].some((r) => p === r || p.startsWith(r + "/")) },
  { href: "/mcp", label: "mcp", match: (p) => p.startsWith("/mcp") },
  { href: "/supercomputer", label: "agentic", mega: "agentic", match: (p) => ["/supercomputer", "/skills", "/katana", "/spaces", "/flows"].some((r) => p.startsWith(r)) },
  { href: "/cinema", label: "studios", mega: "studios", match: (p) => ["/cinema", "/projects", "/factory", "/influencer"].some((r) => p.startsWith(r)) },
];
const PRODUCTS: Item[] = [
  { href: "/cinema", label: "cinema", badge: "new", match: (p) => p.startsWith("/cinema") || p.startsWith("/projects") },
  { href: "/supercomputer", label: "supercomputer", badge: "new", match: (p) => p.startsWith("/supercomputer") },
  { href: "/factory", label: "factory", badge: "new", match: (p) => p.startsWith("/factory") },
  { href: "/katana", label: "katana", badge: "new", match: (p) => p.startsWith("/katana") },
  { href: "/video?tab=genjutsu", label: "genjutsu", badge: "top", match: (p, q) => p.startsWith("/video") && tabIs(q, "genjutsu") },
  { href: "/spaces", label: "spaces", badge: "new", match: (p) => p.startsWith("/spaces") || p.startsWith("/flows") },
  { href: "/influencer", label: "influencer", badge: "new", match: (p) => p.startsWith("/influencer") },
  { href: "/presets?c=Apps", label: "apps", match: (p, q) => p.startsWith("/presets") && q.get("c") === "Apps" },
  { href: "/use-cases", label: "useCases", match: (p) => p.startsWith("/use-cases") },
  { href: "/presets", label: "presets", match: (p, q) => p.startsWith("/presets") && q.get("c") !== "Apps" },
];
/** Lo que no cabe en la barra: el menú «Más». */
const MORE: Item[] = [
  { href: "/models", label: "models", match: (p) => p.startsWith("/models") },
  { href: "/elements", label: "elements", match: (p) => p.startsWith("/elements") },
  { href: "/skills", label: "skills", match: (p) => p.startsWith("/skills") },
  { href: "/history", label: "history", match: (p) => p.startsWith("/history") },
  { href: "/providers", label: "providers", match: (p) => p.startsWith("/providers") },
  { href: "/usage", label: "usage", match: (p) => p.startsWith("/usage") },
];

function Badge({ kind }: { kind: "new" | "top" | "TOP" | "NEW" }) {
  const { t } = useI18n();
  const top = kind.toLowerCase() === "top";
  return (
    <span
      className={clsx(
        "rounded-md px-1.5 py-0.5 text-[10px] leading-3 font-bold",
        top ? "bg-lime text-ink" : "bg-lime/20 text-lime",
      )}
    >
      {top ? t.nav.top : t.nav.new}
    </span>
  );
}

function NavLink({ item, active, onClick, block }: { item: Item; active: boolean; onClick?: () => void; block?: boolean }) {
  const { t } = useI18n();
  return (
    <Link
      href={item.href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "flex items-center gap-1.5 rounded-lg text-sm font-medium tracking-[0.1px] whitespace-nowrap transition-colors",
        block ? "px-2.5 py-2 hover:bg-surface-4" : "px-2 py-1",
        active ? "text-lime" : "text-fg-3 hover:text-fg",
      )}
    >
      {t.nav[item.label]}
      {item.badge && <Badge kind={item.badge} />}
    </Link>
  );
}

const SHOWN = 5; // entradas por columna antes de «Más», como Higgsfield

/** Fila compacta de una columna: icono, nombre y su insignia. La descripción va en el título (al pasar el cursor). */
function MenuItem({ entry, onClick }: { entry: MenuEntry; onClick: () => void }) {
  const { locale } = useI18n();
  const Icon = entry.icon;
  return (
    <Link
      href={entry.href}
      onClick={onClick}
      title={entry.description[locale]}
      className="group flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13.5px] font-medium text-fg hover:bg-surface-4"
    >
      <Icon className="size-4 shrink-0 text-fg-3 group-hover:text-lime" />
      <span className="truncate">{entry.title[locale]}</span>
      {entry.badge && <Badge kind={entry.badge} />}
    </Link>
  );
}

function MenuColumn({ title, entries, onClose }: { title: string; entries: MenuEntry[]; onClose: () => void }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const shown = all ? entries : entries.slice(0, SHOWN);
  return (
    <div className="min-w-0">
      <p className="px-2 pb-1 text-[12px] font-medium text-fg-4">{title}</p>
      {shown.map((e) => (
        <MenuItem key={e.href + e.title.en} entry={e} onClick={onClose} />
      ))}
      {entries.length > SHOWN && (
        <button
          type="button"
          onClick={() => setAll(!all)}
          aria-expanded={all}
          className="flex items-center gap-1 px-2 py-1.5 text-[12.5px] font-medium text-fg-4 hover:text-fg"
        >
          {all ? t.nav.less : t.nav.more}
          <ChevronDown className={clsx("size-3.5 transition-transform", all && "rotate-180")} />
        </button>
      )}
    </div>
  );
}

/** Panel desplegable de una sección, como el de Higgsfield: tarjetas con arte, «Funciones» y «Modelos», y lo destacado. */
function MegaPanel({ menu, onClose }: { menu: MegaMenu; onClose: () => void }) {
  const { t, locale } = useI18n();
  const cardHrefs = new Set(menu.cards.map((c) => c.href));
  const features = menu.features.filter((e) => !cardHrefs.has(e.href)); // lo que ya es tarjeta no se repite
  const Promo = menu.promo.icon;
  return (
    <div className="thin-scrollbar max-h-[calc(100dvh-5rem)] w-[min(720px,calc(100vw-1rem))] overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl">
      <div className={clsx("grid gap-3 border-b border-line pb-3", menu.cards.length % 3 === 0 ? "grid-cols-3" : "grid-cols-4")}>
        {menu.cards.map((c) => {
          const Icon = c.icon;
          return (
            <Link key={c.href} href={c.href} onClick={onClose} className="group block text-center">
              <span className={clsx("relative flex items-center justify-center overflow-hidden rounded-xl border border-line-2 bg-surface-2", menu.cards.length === 3 ? "aspect-[2/1]" : "aspect-[16/10]")}>
                {c.art ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={c.art} alt="" className="size-full object-cover transition-transform duration-300 group-hover:scale-105" />
                ) : (
                  <Icon className="size-8 text-lime" />
                )}
              </span>
              <span className="mt-1.5 block truncate text-[13px] font-medium text-fg group-hover:text-lime">{c.title[locale]}</span>
            </Link>
          );
        })}
      </div>
      {(features.length > 0 || menu.models.length > 0) && (
        <div className="grid grid-cols-2 gap-4 pt-3">
          {features.length > 0 && <MenuColumn title={menu.titles?.[0][locale] ?? t.nav.features} entries={features} onClose={onClose} />}
          {menu.models.length > 0 && <MenuColumn title={menu.titles?.[1][locale] ?? t.nav.modelsCol} entries={menu.models} onClose={onClose} />}
        </div>
      )}
      <div className="pt-3" />
      <Link
        href={menu.promo.href}
        onClick={onClose}
        className="group flex items-center gap-2.5 rounded-xl border border-line-2 bg-surface-2 px-3 py-2.5 text-[13px] hover:border-lime/40"
      >
        {menu.promo.badge ? <Badge kind={menu.promo.badge} /> : <Promo className="size-4 shrink-0 text-fg-3" />}
        <span className="shrink-0 font-semibold text-fg">{menu.promo.title[locale]}</span>
        <span className="min-w-0 truncate text-fg-3">{menu.promo.description[locale]}</span>
        <span className="ml-auto flex shrink-0 items-center gap-0.5 text-fg-4 group-hover:text-lime">
          {t.nav.tryNow}
          <ChevronRight className="size-3.5" />
        </span>
      </Link>
    </div>
  );
}

function NavLinks() {
  const { t, locale } = useI18n();
  const pathname = usePathname();
  const query = useSearchParams();
  const [open, setOpen] = useState(false);
  const [mega, setMega] = useState<MegaMenu["key"] | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const closer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isActive = (item: Item) => item.match(pathname, query);
  const inMenu = MORE.some(isActive);
  const close = () => {
    setOpen(false);
    setMega(null);
  };
  const hover = (key: MegaMenu["key"] | null) => {
    if (closer.current) clearTimeout(closer.current);
    if (key) setMega(key);
    else closer.current = setTimeout(() => setMega(null), 140);
  };
  const menu = MEGA_MENUS.find((m) => m.key === mega);

  // Se cierra con Escape o con un clic fuera del menú.
  useEffect(() => {
    if (!open && !mega) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    const onClick = (e: MouseEvent) => !root.current?.contains(e.target as Node) && close();
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open, mega]);

  return (
    <div ref={root} className="flex min-w-0 flex-1 items-center">
      <div className="hidden shrink-0 items-center lg:flex" onMouseLeave={() => hover(null)}>
        {PRIMARY.map((item) =>
          item.mega ? (
            <div key={item.href} onMouseEnter={() => hover(item.mega!)} onFocus={() => hover(item.mega!)}>
              <NavLink item={item} active={isActive(item) || mega === item.mega} onClick={close} />
            </div>
          ) : (
            <div key={item.href} onMouseEnter={() => hover(null)}>
              <NavLink item={item} active={isActive(item)} />
            </div>
          ),
        )}
        {menu && (
          <div className="absolute top-full left-2 z-50 pt-1" onMouseEnter={() => hover(menu.key)}>
            <MegaPanel menu={menu} onClose={close} />
          </div>
        )}
      </div>
      {/* En escritorio, «Más» se abre bajo su propio botón (lg:relative); en móvil, a todo el ancho de la barra. */}
      <div className="lg:relative">
      <button
        type="button"
        onClick={() => {
          setMega(null);
          setOpen(!open);
        }}
        aria-expanded={open}
        aria-haspopup="true"
        className={clsx(
          "ml-1 flex h-8 shrink-0 items-center gap-1 rounded-lg px-2 text-sm font-medium transition-colors",
          open ? "bg-surface-4 text-fg" : inMenu ? "text-lime" : "text-fg-3 hover:text-fg",
        )}
      >
        <Menu className="size-4 lg:hidden" />
        <span className="hidden lg:inline">{t.nav.more}</span>
        <span className="lg:hidden">{t.nav.menu}</span>
        <ChevronDown className={clsx("hidden size-3.5 transition-transform lg:block", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute inset-x-2 top-full z-50 mt-1 max-h-[calc(100dvh-4rem)] overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl lg:inset-x-auto lg:left-0 lg:w-[260px]">
          {/* En pantallas angostas la barra no muestra las secciones: van aquí, con sus funciones. */}
          <div className="grid grid-cols-2 gap-0.5 border-b border-line pb-3 sm:grid-cols-4 lg:hidden">
            {[...PRIMARY, ...PRODUCTS].map((item) => (
              <NavLink key={item.label} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 border-b border-line py-3 sm:grid-cols-3 lg:hidden">{/* Imagen, Video, Audio, Agentes y Estudios */}
            {MEGA_MENUS.map((m) => (
              <div key={m.key}>
                <p className="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{t.nav[m.key]}</p>
                {(m.features.length ? m.features : m.cards).map((e) => (
                  <Link key={e.href + e.title.en} href={e.href} onClick={close} className="block rounded-lg px-2.5 py-1.5 text-sm text-fg-3 hover:bg-surface-4 hover:text-fg">
                    {e.title[locale]}
                  </Link>
                ))}
              </div>
            ))}
          </div>
          {/* Los productos van en Agentes y Estudios (como en Higgsfield); aquí también, todos juntos. */}
          <div className="hidden border-b border-line pb-3 lg:block">
            {PRODUCTS.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
          <div className="pt-3">
            <p className="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{t.nav.groupAccount}</p>
            {MORE.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

function ApiStatus() {
  const { t } = useI18n();
  const [state, setState] = useState<"checking" | "online" | "offline" | "nokeys">("checking");
  useEffect(() => {
    let alive = true;
    const check = () =>
      fetch("/api/studio/health")
        .then((r) => r.json())
        .then((b) => alive && setState(b.ok ? (b.higgsfield_configured ? "online" : "nokeys") : "offline"))
        .catch(() => alive && setState("offline"));
    check();
    const t = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  const label = t.nav.status[state];
  return (
    <span className="hidden items-center gap-2 rounded-lg bg-glass px-2.5 py-1 text-sm font-medium text-fg-2 xl:flex">
      <span
        className={clsx(
          "size-1.5 rounded-full",
          state === "online" ? "bg-success" : state === "checking" ? "bg-fg-3" : state === "nokeys" ? "bg-warning" : "bg-danger",
        )}
      />
      {label}
    </span>
  );
}

/** Proyecto activo: a dónde va lo que se genera. Lleva a su página; la x deja de trabajar en él. */
function ActiveProjectPill() {
  const { t } = useI18n();
  const project = useActiveProject();
  if (!project) return null;
  return (
    <span className="flex h-8 max-w-48 items-center rounded-lg bg-lime/10 text-sm font-medium text-lime">
      <Link href={`/cinema/${project.id}`} title={t.projects.activeHint} className="flex min-w-0 items-center gap-1.5 pl-2.5">
        <FolderOpen className="size-4 shrink-0" />
        <span className="truncate">{project.name}</span>
      </Link>
      <button type="button" onClick={() => setActiveProject(null)} aria-label={t.projects.deactivate} title={t.projects.deactivate} className="px-1.5 text-lime/70 hover:text-lime">
        <X className="size-3.5" />
      </button>
    </span>
  );
}

/** Alterna ES/EN; el idioma se guarda en una cookie y el español es el predeterminado. */
function LanguageToggle() {
  const { t, locale, setLocale } = useI18n();
  const next = locale === "es" ? "en" : "es";
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      title={t.nav.switchTo}
      aria-label={`${t.nav.language}: ${locale.toUpperCase()}. ${t.nav.switchTo}`}
      className="flex h-8 items-center gap-1.5 rounded-lg bg-glass px-2 text-xs font-semibold text-fg-2 transition-colors hover:text-fg"
    >
      <Globe className="size-4" />
      {locale.toUpperCase()}
    </button>
  );
}

/** Cierra la sesión de la puerta de acceso (solo se muestra con STUDIO_PASSWORD). */
function SignOut() {
  const { t } = useI18n();
  async function signOut() {
    await fetch("/api/session", { method: "DELETE" }).catch(() => {});
    window.location.assign("/login");
  }
  return (
    <button type="button" onClick={signOut} aria-label={t.login.logout} title={t.login.logout} className="rounded-lg p-1.5 text-fg-3 hover:text-fg">
      <LogOut className="size-4" />
    </button>
  );
}

export function Nav({ gate = false }: { gate?: boolean }) {
  const { t } = useI18n();
  const pathname = usePathname();
  if (pathname === "/login") return null;
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 bg-page/95 px-4 backdrop-blur-md">
      <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="HF Studio">
        <Logo />
        <span className="hidden flex-col leading-tight min-[1800px]:flex">
          <span className="text-[15px] font-semibold tracking-[-0.01em]">HF Studio</span>
          <span className="text-[10.5px] text-fg-3">{t.meta.tagline}</span>
        </span>
      </Link>
      <Suspense fallback={<div className="flex-1" />}>
        <NavLinks />
      </Suspense>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <ActiveProjectPill />
        <Approvals />
        <ApiStatus />
        <LanguageToggle />
        {gate && <SignOut />}
        <span className="mx-1 hidden h-4 w-px bg-line-2 lg:block" />
        <Link
          href="/history"
          className="rounded-lg bg-lime/8 px-2.5 py-1 text-sm font-medium text-lime shadow-[inset_0_2px_3px_rgba(255,255,255,0.03)]"
        >
          {t.nav.library}
        </Link>
        <Link href="/video" className="flex items-center gap-1 rounded-lg bg-lime px-2.5 py-1 text-sm font-medium text-[#1a1a1a]">
          <Sparkles className="size-3.5" />
          {t.nav.create}
        </Link>
      </div>
    </header>
  );
}
