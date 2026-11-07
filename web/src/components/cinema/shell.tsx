"use client";

import clsx from "clsx";
import { Clapperboard, Menu, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import type { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Masonry } from "@/components/masonry";
import { modelMap, reuseHref, studio } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";

/**
 * Armazón de Cinema Studio: barra lateral (en móvil, un cajón que se abre con el botón de menú) y el área principal.
 * `children` recibe el botón que abre el cajón para ponerlo en su barra superior.
 */
export function CinemaShell({ sidebar, children }: { sidebar: (close: () => void) => ReactNode; children: (menuButton: ReactNode) => ReactNode }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const menuButton = (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label={t.cinemaStudio.openSidebar}
      className="flex size-9 shrink-0 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-3 hover:text-fg md:hidden"
    >
      <Menu className="size-5" />
    </button>
  );
  return (
    <div className="flex h-[calc(100dvh-3.5rem)] min-h-0 overflow-hidden">
      {open && <div className="fixed inset-0 z-40 bg-black/60 md:hidden" onClick={close} />}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-50 flex w-[260px] shrink-0 flex-col border-r border-line bg-surface-1 transition-transform md:static md:z-auto md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          type="button"
          onClick={close}
          aria-label={t.cinemaStudio.closeSidebar}
          className="absolute top-3 right-3 rounded-lg p-1 text-fg-3 hover:text-fg md:hidden"
        >
          <X className="size-5" />
        </button>
        {sidebar(close)}
      </aside>
      <div className="relative flex min-w-0 flex-1 flex-col">{children(menuButton)}</div>
    </div>
  );
}

/** Cabecera de la barra lateral con el nombre de la sección. */
export function SidebarBrand() {
  const { t } = useI18n();
  return (
    <Link href="/cinema" className="mb-2 flex h-11 items-center gap-2.5 rounded-xl bg-surface-3 px-2.5 text-[16px] font-semibold">
      <span className="flex size-7 items-center justify-center rounded-lg bg-lime text-ink">
        <Clapperboard className="size-4" />
      </span>
      {t.cinemaStudio.title}
    </Link>
  );
}

/** Fila de la barra lateral: enlace o botón, con icono y estado activo. */
export function SideItem({
  icon,
  label,
  active,
  href,
  onClick,
  trailing,
  small,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  href?: string;
  onClick?: () => void;
  trailing?: ReactNode;
  small?: boolean;
}) {
  const className = clsx(
    "flex w-full min-w-0 items-center gap-3 rounded-xl px-2 text-left font-medium transition-colors",
    small ? "h-9 text-[14px]" : "h-10 text-[15px]",
    active ? "bg-surface-4 text-fg" : "text-fg-2 hover:bg-surface-3 hover:text-fg",
  );
  const body = (
    <>
      <span className={clsx("flex shrink-0 items-center justify-center rounded-lg bg-surface-4 text-fg-2", small ? "size-6" : "size-7")}>{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {trailing}
    </>
  );
  return href ? (
    <Link href={href} onClick={onClick} className={className}>
      {body}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className}>
      {body}
    </button>
  );
}

/** Menú pequeño que se abre bajo un botón (Filtrar, Vista, ⋮); clic fuera o Escape lo cierran. */
export function Dropdown({
  trigger,
  children,
  align = "right",
  className,
  buttonClassName,
  label,
}: {
  trigger: ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  className?: string;
  buttonClassName?: string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          buttonClassName ?? "flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm font-medium text-fg-2 hover:bg-surface-3 hover:text-fg",
          open && "bg-surface-3 text-fg",
        )}
      >
        {trigger}
      </button>
      {open && (
        <div
          className={clsx(
            "absolute top-full z-40 mt-1.5 rounded-xl border border-line-2 bg-surface-2 p-1 shadow-2xl",
            align === "right" ? "right-0" : "left-0",
            className ?? "w-56",
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

/** Rejilla de generaciones (Mis generaciones, Mis favoritas). */
export function GenerationsGrid({ list, items, empty }: { list: ReturnType<typeof useGenerations>; items: Generation[]; empty: string }) {
  const router = useRouter();
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());
  useEffect(() => {
    studio.models().then((r) => setModels(modelMap(r.models))).catch(() => undefined);
  }, []);
  if (list.loading) return <div className="shimmer h-60 rounded-2xl" />;
  if (!items.length) return <p className="mt-16 text-center text-fg-3">{empty}</p>;
  return (
    <Masonry
      items={items}
      itemKey={(g) => g.id}
      maxColumns={4}
      minColumnWidth={220}
      gap={12}
      render={(g) => (
        <GenerationCard
          g={g}
          layout="grid"
          models={models}
          gallery={items}
          onReuse={(x) => router.push(reuseHref(x.model, x.id, models))}
          onDelete={list.remove}
          onFavorite={(x) => void list.setFavorite([x.id], !x.favorite).catch(() => undefined)}
        />
      )}
    />
  );
}
