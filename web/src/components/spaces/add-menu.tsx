"use client";

import clsx from "clsx";
import { AudioLines, ImageIcon, Search, StickyNote, Type, Upload, Video, Wrench } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { matchesModel, workflowLabel } from "@/lib/i18n/workflow";
import { isAudioNode, isTool, type PortKind } from "@/lib/spaces";
import { modelLabel } from "@/lib/studio";
import type { ModelSummary } from "@/lib/types";

export type AddChoice = { type: "text" | "media" | "note" } | { type: "generator"; model: string };

type Item = { key: string; choice: AddChoice; icon: typeof Type; title: string; hint: string; group: string };

/**
 * Spotlight del lienzo: nodos básicos y todos los modelos del catálogo, con búsqueda. Si se abre al soltar
 * una conexión (`from`), solo ofrece modelos con un puerto de ese tipo, porque el nodo nuevo queda conectado.
 */
export function AddMenu({
  at,
  from,
  models,
  onPick,
  onClose,
}: {
  at: { x: number; y: number } | null;
  from: PortKind | null;
  models: ModelSummary[];
  onPick: (choice: AddChoice) => void;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const s = t.spaces;
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const items = useMemo(() => {
    const base: Item[] = from
      ? []
      : [
          { key: "text", choice: { type: "text" }, icon: Type, title: s.addText, hint: s.addTextHint, group: "" },
          { key: "media", choice: { type: "media" }, icon: Upload, title: s.addMedia, hint: s.addMediaHint, group: "" },
          { key: "note", choice: { type: "note" }, icon: StickyNote, title: s.addNote, hint: s.addNoteHint, group: "" },
        ];
    const query = q.trim().toLowerCase();
    const nodes = base.filter((i) => !query || i.title.toLowerCase().includes(query));
    const gens = models
      .filter((m) => m.output === "image" || m.output === "video" || isAudioNode(m.id))
      .filter((m) => !from || (m.inputs ?? []).includes(from))
      // Las herramientas se encuentran también por el nombre y la descripción que se muestran (revisión 58).
      .filter((m) =>
        matchesModel(m, q.trim(), locale, `${s.toolNames[m.id] ?? s.audioNames[m.id] ?? ""} ${s.toolHints[m.id] ?? s.audioHints[m.id] ?? ""}`),
      )
      .map<Item>((m) => {
        const { name, workflow } = modelLabel(m.title);
        if (isAudioNode(m.id))
          return { key: m.id, choice: { type: "generator", model: m.id }, icon: AudioLines, title: s.audioNames[m.id] ?? name, hint: s.audioHints[m.id] ?? "", group: s.audioGroup };
        if (isTool(m.id)) {
          const title = s.toolNames[m.id] ?? name;
          return { key: m.id, choice: { type: "generator", model: m.id }, icon: Wrench, title, hint: s.toolHints[m.id] ?? "", group: s.tools };
        }
        return {
          key: m.id,
          choice: { type: "generator", model: m.id },
          icon: m.output === "video" ? Video : ImageIcon,
          title: name,
          hint: workflowLabel(workflow || m.workflow, locale),
          group: m.output === "video" ? s.addVideo : s.addImage,
        };
      });
    const groups = [s.tools, s.audioGroup, s.addImage, s.addVideo];
    return [...nodes, ...groups.flatMap((g) => gens.filter((x) => x.group === g))];
  }, [from, models, q, locale, s]);

  useEffect(() => {
    if (!at) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [at, onClose]);

  if (!at) return null;
  const left = Math.max(12, Math.min(at.x, window.innerWidth - 392));
  const top = Math.max(12, Math.min(at.y, window.innerHeight - 452));
  const current = Math.min(active, items.length - 1);

  function choose(item: Item | undefined) {
    if (!item) return;
    onPick(item.choice);
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50" onClick={onClose}>
      <div
        className="absolute flex max-h-[440px] w-[380px] flex-col overflow-hidden rounded-2xl border border-line-2 bg-surface-2 shadow-2xl"
        style={{ left, top }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
          <Search className="size-4 text-fg-3" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(a + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(a - 1, 0));
              } else if (e.key === "Enter") {
                choose(items[current]);
              }
            }}
            placeholder={s.search}
            className="flex-1 bg-transparent text-[14px] outline-none placeholder:text-fg-3"
          />
        </div>
        <div className="thin-scrollbar overflow-y-auto p-1.5">
          {items.length === 0 && <p className="p-5 text-center text-sm text-fg-3">{s.noResults}</p>}
          {items.map((item, i) => {
            const Icon = item.icon;
            const header = item.group && item.group !== items[i - 1]?.group;
            return (
              <div key={item.key}>
                {header && <p className="px-2.5 pt-2.5 pb-1 text-[11px] font-semibold tracking-wide text-fg-3 uppercase">{item.group}</p>}
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(item)}
                  className={clsx("flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left", i === current ? "bg-glass" : "")}
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-4">
                    <Icon className="size-4 text-fg-2" />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[14px] font-semibold">{item.title}</span>
                    <span className="block truncate text-[12px] text-fg-3">{item.hint}</span>
                  </span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
