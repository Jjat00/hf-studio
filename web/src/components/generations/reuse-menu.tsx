"use client";

import clsx from "clsx";
import { Loader2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio } from "@/lib/studio";
import type { Generation } from "@/lib/types";

type Target = { key: "animate" | "videoReference" | "editImage" | "element" | "editVideo" | "extend" | "motion"; href: string };

// A dónde llevar una creación según lo que es. El estudio pone la URL en la primera casilla del tipo (?use=&as=).
const TARGETS: Record<"image" | "video", Target[]> = {
  image: [
    { key: "animate", href: "/video?tab=create&mode=frames" },
    { key: "videoReference", href: "/video?tab=create&mode=references" },
    { key: "editImage", href: "/image?tab=create&mode=edit" },
    { key: "element", href: "/elements" },
  ],
  video: [
    { key: "editVideo", href: "/video?tab=edit&mode=edit" },
    { key: "extend", href: "/video?tab=edit&mode=extend" },
    { key: "videoReference", href: "/video?tab=create&mode=references" },
    { key: "motion", href: "/video?tab=motion" },
  ],
};

/** Menú «Usar en…» de una creación terminada: la abre como entrada de otra generación (o de un elemento). */
export function ReuseMenu({ g, className }: { g: Generation; className: string }) {
  const { t } = useI18n();
  const r = t.reuseAs;
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [alignLeft, setAlignLeft] = useState(false); // abre hacia donde haya espacio (primera columna)
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const kind = g.outputs[0]?.kind;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (g.status !== "completed" || (kind !== "image" && kind !== "video")) return null;

  async function go(target: Target) {
    setBusy(true);
    setError(null);
    try {
      const { url } = await studio.useOutput(g.id, 0);
      const sep = target.href.includes("?") ? "&" : "?";
      const q = target.key === "element" ? `image=${encodeURIComponent(url)}` : `use=${encodeURIComponent(url)}&as=${kind}`;
      setOpen(false);
      router.push(`${target.href}${sep}${q}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        title={r.menu}
        aria-label={r.menu}
        onClick={(e) => {
          setAlignLeft(e.currentTarget.getBoundingClientRect().left < 260);
          setOpen((o) => !o);
        }}
        className={className}
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
      </button>
      {open && (
        <div
          className={clsx(
            "absolute bottom-full z-20 mb-2 w-56 rounded-xl border border-line bg-surface-1 p-1 shadow-xl",
            alignLeft ? "left-0" : "right-0",
          )}
        >
          <p className="px-2.5 py-1.5 text-xs font-semibold text-fg-3">{busy ? r.working : r.menu}</p>
          {TARGETS[kind].map((target) => (
            <button
              key={target.key}
              type="button"
              disabled={busy}
              onClick={() => go(target)}
              className="block w-full rounded-lg px-2.5 py-2 text-left text-sm text-fg-2 hover:bg-glass hover:text-fg disabled:opacity-50"
            >
              {r[target.key]}
            </button>
          ))}
          {error && <p className="px-2.5 py-1.5 text-xs text-danger">{error}</p>}
        </div>
      )}
    </div>
  );
}
