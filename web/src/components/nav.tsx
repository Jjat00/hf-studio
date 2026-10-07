"use client";

import clsx from "clsx";
import { ChevronDown, Globe, Menu, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import type { Dict } from "@/lib/i18n";
import { useI18n } from "./i18n-provider";
import { Logo } from "./logo";

type Label = Exclude<keyof Dict["nav"], "status">;
type Item = { href: string; label: Label; badge?: boolean; match: (p: string, tab: string | null) => boolean };

const PRIMARY: Item[] = [
  { href: "/", label: "explore", match: (p) => p === "/" },
  { href: "/image", label: "image", match: (p) => p.startsWith("/image") },
  { href: "/video", label: "video", match: (p, t) => p.startsWith("/video") && (!t || t === "create") },
  { href: "/use-cases", label: "useCases", badge: true, match: (p) => p.startsWith("/use-cases") },
  { href: "/presets", label: "presets", match: (p) => p.startsWith("/presets") },
  { href: "/spaces", label: "spaces", badge: true, match: (p) => p.startsWith("/spaces") },
  { href: "/mcp", label: "mcp", match: (p) => p.startsWith("/mcp") },
  { href: "/models", label: "models", match: (p) => p.startsWith("/models") },
];
/** Lo que no cabe en la barra: el menú «Más», agrupado por tema. */
const GROUPS: { label: Label; items: Item[] }[] = [
  {
    label: "groupVideo",
    items: [
      { href: "/video?tab=genjutsu", label: "genjutsu", match: (p, t) => p.startsWith("/video") && t === "genjutsu" },
      { href: "/video?tab=edit", label: "editVideo", match: (p, t) => p.startsWith("/video") && t === "edit" },
      { href: "/video?tab=motion", label: "motionControl", match: (p, t) => p.startsWith("/video") && t === "motion" },
      { href: "/elements", label: "elements", match: (p) => p.startsWith("/elements") },
    ],
  },
  {
    label: "groupAudio",
    items: [
      { href: "/voice", label: "voice", match: (p) => p === "/voice" || p.startsWith("/voice/") },
      { href: "/voices", label: "voices", match: (p) => p.startsWith("/voices") },
      { href: "/audio", label: "audio", match: (p) => p.startsWith("/audio") },
      { href: "/sounds", label: "sounds", match: (p) => p.startsWith("/sounds") },
    ],
  },
  {
    label: "groupAccount",
    items: [
      { href: "/history", label: "history", match: (p) => p.startsWith("/history") },
      { href: "/providers", label: "providers", match: (p) => p.startsWith("/providers") },
      { href: "/usage", label: "usage", match: (p) => p.startsWith("/usage") },
    ],
  },
];

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
      {item.badge && (
        <span className="rounded-md bg-lime/20 px-1.5 py-0.5 text-[10px] leading-3 font-bold text-lime">{t.nav.new}</span>
      )}
    </Link>
  );
}

function NavLinks() {
  const { t } = useI18n();
  const pathname = usePathname();
  const tab = useSearchParams().get("tab");
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const isActive = (item: Item) => item.match(pathname, tab);
  const inMenu = GROUPS.some((g) => g.items.some(isActive));
  const close = () => setOpen(false);

  // Se cierra con Escape o con un clic fuera del menú.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onClick = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  return (
    <div ref={root} className="flex min-w-0 flex-1 items-center">
      <div className="hide-scrollbar hidden min-w-0 items-center overflow-x-auto lg:flex">
        {PRIMARY.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item)} />
        ))}
      </div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
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
        <div className="absolute inset-x-2 top-full z-50 mt-1 max-h-[calc(100dvh-4rem)] overflow-y-auto rounded-2xl border border-line-2 bg-surface-3 p-3 shadow-2xl lg:inset-x-auto lg:left-1/2 lg:w-[640px] lg:-translate-x-1/2">
          {/* En pantallas angostas la barra no muestra las secciones principales: van aquí arriba. */}
          <div className="grid grid-cols-2 gap-0.5 border-b border-line pb-3 sm:grid-cols-4 lg:hidden">
            {PRIMARY.map((item) => (
              <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3 pt-3 sm:grid-cols-3 lg:pt-0">
            {GROUPS.map((group) => (
              <div key={group.label}>
                <p className="px-2.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{t.nav[group.label]}</p>
                {group.items.map((item) => (
                  <NavLink key={item.href} item={item} active={isActive(item)} onClick={close} block />
                ))}
              </div>
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
