"use client";

import clsx from "clsx";
import { Globe, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
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
  { href: "/mcp", label: "mcp", match: (p) => p.startsWith("/mcp") },
  { href: "/models", label: "models", match: (p) => p.startsWith("/models") },
];
const SECONDARY: Item[] = [
  { href: "/video?tab=genjutsu", label: "genjutsu", match: (p, t) => p.startsWith("/video") && t === "genjutsu" },
  { href: "/video?tab=edit", label: "editVideo", match: (p, t) => p.startsWith("/video") && t === "edit" },
  { href: "/video?tab=motion", label: "motionControl", match: (p, t) => p.startsWith("/video") && t === "motion" },
  { href: "/history", label: "history", match: (p) => p.startsWith("/history") },
];

function NavLinks() {
  const { t } = useI18n();
  const pathname = usePathname();
  const tab = useSearchParams().get("tab");
  const link = (item: Item) => {
    const active = item.match(pathname, tab);
    return (
      <Link
        key={item.href}
        href={item.href}
        className={clsx(
          "flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-medium tracking-[0.1px] whitespace-nowrap transition-colors",
          active ? "text-lime" : "text-fg-3 hover:text-fg",
        )}
      >
        {t.nav[item.label]}
        {item.badge && (
          <span className="rounded-md bg-lime/20 px-1.5 py-0.5 text-[10px] leading-3 font-bold text-lime">{t.nav.new}</span>
        )}
      </Link>
    );
  };
  return (
    <div className="hide-scrollbar flex min-w-0 items-center overflow-x-auto">
      {PRIMARY.map(link)}
      <span className="mx-2 h-4 w-px shrink-0 bg-line-2" />
      {SECONDARY.map(link)}
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
