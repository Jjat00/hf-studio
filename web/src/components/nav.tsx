"use client";

import clsx from "clsx";
import { ChevronDown, Globe, Menu, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import type { Dict } from "@/lib/i18n";
import { MEGA_MENUS, type MegaMenu, type MenuEntry } from "@/lib/menu";
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
];
const PRODUCTS: Item[] = [
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

function MenuRow({ entry, onClick }: { entry: MenuEntry; onClick: () => void }) {
  const { locale } = useI18n();
  const Icon = entry.icon;
  return (
    <Link href={entry.href} onClick={onClick} className="group flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface-4">
      <span className="relative flex size-10 shrink-0 items-center justify-center rounded-xl border border-line-2 bg-surface-2 text-fg-2 group-hover:text-lime">
        <Icon className="size-[18px]" />
        {entry.badge && (
          <span className="absolute -top-1.5 -left-1.5">
            <Badge kind={entry.badge} />
          </span>
        )}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[14px] font-medium text-fg">{entry.title[locale]}</span>
        <span className="block truncate text-[12.5px] text-fg-3">{entry.description[locale]}</span>
      </span>
    </Link>
  );
}

/** Panel desplegable de una sección: «Funciones» a la izquierda y «Modelos» a la derecha. */
function MegaPanel({ menu, onClose }: { menu: MegaMenu; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="thin-scrollbar grid max-h-[calc(100dvh-5rem)] w-[min(880px,calc(100vw-1rem))] grid-cols-2 gap-4 overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl">
      {[
        [t.nav.features, menu.features],
        [t.nav.modelsCol, menu.models],
      ].map(([title, entries]) => (
        <div key={title as string} className="min-w-0">
          <p className="px-2 pb-1.5 text-[12px] font-medium text-fg-4">{title as string}</p>
          {(entries as MenuEntry[]).map((e) => (
            <MenuRow key={e.href + e.title.en} entry={e} onClick={onClose} />
          ))}
        </div>
      ))}
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
      <div className="hidden min-w-0 items-center lg:flex" onMouseLeave={() => hover(null)}>
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
      <span className="mx-2 hidden h-4 w-px shrink-0 bg-line-2 lg:block" />
      <div className="hide-scrollbar hidden min-w-0 items-center overflow-x-auto lg:flex">
        {PRODUCTS.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item)} />
        ))}
      </div>
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
        <div className="absolute inset-x-2 top-full z-50 mt-1 max-h-[calc(100dvh-4rem)] overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl lg:inset-x-auto lg:right-2 lg:w-[260px]">
          {/* En pantallas angostas la barra no muestra las secciones: van aquí, con sus funciones. */}
          <div className="grid grid-cols-2 gap-0.5 border-b border-line pb-3 sm:grid-cols-4 lg:hidden">
            {[...PRIMARY, ...PRODUCTS].map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-3 border-b border-line py-3 sm:grid-cols-3 lg:hidden">
            {MEGA_MENUS.map((m) => (
              <div key={m.key}>
                <p className="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{t.nav[m.key]}</p>
                {m.features.map((e) => (
                  <Link key={e.href + e.title.en} href={e.href} onClick={close} className="block rounded-lg px-2.5 py-1.5 text-sm text-fg-3 hover:bg-surface-4 hover:text-fg">
                    {e.title[locale]}
                  </Link>
                ))}
              </div>
            ))}
          </div>
          <div className="pt-3 lg:pt-0">
            <p className="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{t.nav.groupAccount}</p>
            {MORE.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
        </div>
      )}
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
    <span className="hidden items-center gap-2 rounded-lg bg-glass px-2.5 py-1 text-sm font-medium text-fg-2 md:flex">
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

export function Nav() {
  const { t } = useI18n();
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 bg-page/95 px-4 backdrop-blur-md">
      <Link href="/" className="shrink-0" aria-label="HF Studio">
        <Logo />
      </Link>
      <Suspense fallback={<div className="flex-1" />}>
        <NavLinks />
      </Suspense>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <ApiStatus />
        <LanguageToggle />
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
