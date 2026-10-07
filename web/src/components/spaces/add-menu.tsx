"use client";

import clsx from "clsx";
import {
  ArrowRight,
  AudioLines,
  Film,
  FolderOpen,
  ImageIcon,
  ListChecks,
  Pin,
  Search,
  Shuffle,
  Sparkles,
  StickyNote,
  Type,
  Upload,
  Video,
  Wand2,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { matchesModel, workflowLabel } from "@/lib/i18n/workflow";
import { isAssistant, isAudioNode, isTool, KIND_COLOR, type PortKind } from "@/lib/spaces";
import { modelLabel } from "@/lib/studio";
import type { ModelSummary } from "@/lib/types";

/** `preset`: valores y variantes con los que nace un nodo de acción (atajo a un modelo del catálogo). */
export type AddChoice =
  | { type: "text" | "media" | "note" | "list" }
  | { type: "asset"; kind: "image" | "video" }
  | { type: "generator"; model: string; preset?: { values?: Record<string, unknown>; count?: number } };

type Tab = "all" | "image" | "video" | "audio" | "utility";
type Item = {
  key: string;
  choice: AddChoice;
  icon: typeof Type;
  title: string;
  hint: string;
  group: string;
  tab: Exclude<Tab, "all">;
  model?: ModelSummary;
};

/**
 * Nodos de acción, como en Magnific: atajos a un modelo del catálogo para una tarea concreta. Se usa el primer
 * modelo de la lista que exista en el catálogo.
 */
const ACTIONS: { key: string; models: string[]; tab: "image" | "video"; icon: typeof Type; preset?: { values?: Record<string, unknown>; count?: number } }[] = [
  { key: "editImage", models: ["alibaba/qwen-image-3/edit"], tab: "image", icon: Wand2 },
  { key: "variations", models: ["alibaba/qwen-image-3/edit"], tab: "image", icon: Shuffle, preset: { values: { prompt: "A new variation of this image: same subject and style, different composition" }, count: 4 } },
  { key: "modifyVideo", models: ["kling-video/o3/video-edit", "bytedance/seedance-2.5/video-edit", "kling-video/omni/video-edit"], tab: "video", icon: Film },
  { key: "extendVideo", models: ["bytedance/seedance-2.5/video-extend"], tab: "video", icon: ArrowRight },
  { key: "motion", models: ["kling-video/v3/motion-control/std", "kling-video/motion-control/std"], tab: "video", icon: Video },
  { key: "objectSwap", models: ["higgsfiled/genjutsu/object-swap/v1.0"], tab: "video", icon: Shuffle },
];

const PINNED_KEY = "hfs.spaces.pinned";

function loadPinned(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(PINNED_KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/**
 * Spotlight del lienzo: pestañas por tipo, fijados, medios propios (Assets), acciones y todos los modelos del
 * catálogo, con búsqueda y una vista previa del elegido. Si se abre al soltar una conexión (`from`), solo ofrece
 * modelos con un puerto de ese tipo, porque el nodo nuevo queda conectado.
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
  const [tab, setTab] = useState<Tab>("all");
  const [active, setActive] = useState(0);
  const [pinned, setPinned] = useState<string[]>(loadPinned);

  const togglePin = (key: string) =>
    setPinned((prev) => {
      const next = prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key];
      try {
        localStorage.setItem(PINNED_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });

  const items = useMemo(() => {
    // Sin tildes ni mayúsculas, como matchesModel: «imagenes» encuentra «Mis imágenes».
    const fold = (x: string) => x.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
    const query = fold(q.trim());
    const byId = new Map(models.map((m) => [m.id, m]));
    const fits = (m: ModelSummary | undefined) => !!m && (!from || (m.inputs ?? []).includes(from));
    const textMatch = (i: Pick<Item, "title" | "hint">) => !query || fold(`${i.title} ${i.hint}`).includes(query);

    const base: Item[] = from
      ? []
      : [
          { key: "text", choice: { type: "text" }, icon: Type, title: s.addText, hint: s.addTextHint, group: s.groupBasics, tab: "utility" },
          { key: "media", choice: { type: "media" }, icon: Upload, title: s.addMedia, hint: s.addMediaHint, group: s.groupBasics, tab: "utility" },
          { key: "list", choice: { type: "list" }, icon: ListChecks, title: s.addList, hint: s.addListHint, group: s.groupBasics, tab: "utility" },
          { key: "note", choice: { type: "note" }, icon: StickyNote, title: s.addNote, hint: s.addNoteHint, group: s.groupBasics, tab: "utility" },
          { key: "asset:image", choice: { type: "asset", kind: "image" }, icon: FolderOpen, title: s.assetImages, hint: s.assetsHint, group: s.groupAssets, tab: "image" },
          { key: "asset:video", choice: { type: "asset", kind: "video" }, icon: FolderOpen, title: s.assetVideos, hint: s.assetsHint, group: s.groupAssets, tab: "video" },
        ];

    const actions: Item[] = [];
    for (const a of ACTIONS) {
      const model = a.models.map((id) => byId.get(id)).find(fits);
      if (!model) continue;
      const name = s.actionNames[a.key] ?? a.key;
      actions.push({ key: `action:${a.key}`, choice: { type: "generator", model: model.id, preset: a.preset }, icon: a.icon, title: name, hint: s.actionHints[a.key] ?? "", group: s.groupActions, tab: a.tab, model });
    }

    const gens = models
      .filter((m) => m.output === "image" || m.output === "video" || isAudioNode(m.id) || isAssistant(m.id))
      .filter(fits)
      .map<Item>((m) => {
        const { name, workflow } = modelLabel(m.title);
        const choice: AddChoice = { type: "generator", model: m.id };
        if (isAssistant(m.id)) return { key: m.id, choice, icon: Sparkles, title: s.assistantName, hint: s.assistantHint, group: s.assistantGroup, tab: "utility", model: m };
        if (isAudioNode(m.id)) return { key: m.id, choice, icon: AudioLines, title: s.audioNames[m.id] ?? name, hint: s.audioHints[m.id] ?? "", group: s.audioGroup, tab: "audio", model: m };
        if (isTool(m.id)) return { key: m.id, choice, icon: Wrench, title: s.toolNames[m.id] ?? name, hint: s.toolHints[m.id] ?? "", group: s.tools, tab: "utility", model: m };
        const video = m.output === "video";
        return { key: m.id, choice, icon: video ? Video : ImageIcon, title: name, hint: workflowLabel(workflow || m.workflow, locale), group: video ? s.addVideo : s.addImage, tab: video ? "video" : "image", model: m };
      });

    // Los modelos se buscan también por id y flujo (matchesModel); el resto por su nombre y descripción.
    const matches = (i: Item) => (i.model && !i.key.startsWith("action:") ? matchesModel(i.model, q.trim(), locale, `${i.title} ${i.hint}`) : textMatch(i));
    const all = [...base, ...actions, ...gens].filter((i) => (tab === "all" || i.tab === tab) && matches(i));
    const pins = all.filter((i) => pinned.includes(i.key)).map((i) => ({ ...i, key: `pin:${i.key}`, group: s.groupPinned }));
    const order = [s.groupBasics, s.groupAssets, s.groupActions, s.assistantGroup, s.tools, s.audioGroup, s.addImage, s.addVideo];
    return [...pins, ...order.flatMap((g) => all.filter((x) => x.group === g))];
  }, [from, models, q, tab, locale, s, pinned]);

  useEffect(() => {
    if (!at) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [at, onClose]);

  if (!at) return null;
  const left = Math.max(12, Math.min(at.x, window.innerWidth - 392));
  const top = Math.max(12, Math.min(at.y, window.innerHeight - 492));
  const current = Math.min(active, items.length - 1);
  const focused = items[current];
  const previewLeft = left + 392 + 260 <= window.innerWidth;

  function choose(item: Item | undefined) {
    if (!item) return;
    onPick(item.choice);
    onClose();
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "all", label: s.tabAll },
    { id: "image", label: s.tabImage },
    { id: "video", label: s.tabVideo },
    { id: "audio", label: s.tabAudio },
    { id: "utility", label: s.tabUtility },
  ];

  return (
    <div className="fixed inset-0 z-50" onClick={onClose}>
      <div
        className="absolute flex max-h-[480px] w-[380px] flex-col overflow-hidden rounded-2xl border border-line-2 bg-surface-2 shadow-2xl"
        style={{ left, top }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-line px-3.5 py-2.5">
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
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-2.5 py-2">
          {tabs.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => {
                setTab(x.id);
                setActive(0);
              }}
              className={clsx("shrink-0 rounded-full px-2.5 py-1 text-[12px]", tab === x.id ? "bg-surface-5 text-fg" : "bg-surface-3 text-fg-3 hover:text-fg")}
            >
              {x.label}
            </button>
          ))}
        </div>
        <div className="thin-scrollbar overflow-y-auto p-1.5">
          {items.length === 0 && <p className="p-5 text-center text-sm text-fg-3">{s.noResults}</p>}
          {items.map((item, i) => {
            const Icon = item.icon;
            const header = item.group && item.group !== items[i - 1]?.group;
            const pinKey = item.key.replace(/^pin:/, "");
            const isPinned = pinned.includes(pinKey);
            return (
              <div key={item.key}>
                {header && <p className="px-2.5 pt-2.5 pb-1 text-[11px] font-semibold tracking-wide text-fg-3 uppercase">{item.group}</p>}
                <div
                  onMouseEnter={() => setActive(i)}
                  className={clsx("group flex w-full items-center gap-3 rounded-xl px-2.5 py-2", i === current ? "bg-glass" : "")}
                >
                  <button type="button" onClick={() => choose(item)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-4">
                      <Icon className="size-4 text-fg-2" />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[14px] font-semibold">{item.title}</span>
                      <span className="block truncate text-[12px] text-fg-3">{item.hint}</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    title={isPinned ? s.unpin : s.pin}
                    aria-label={isPinned ? s.unpin : s.pin}
                    onClick={() => togglePin(pinKey)}
                    className={clsx("rounded-md p-1 transition", isPinned ? "text-lime" : "text-fg-4 opacity-0 group-hover:opacity-100 hover:text-fg focus-visible:opacity-100")}
                  >
                    <Pin className="size-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex shrink-0 gap-3 border-t border-line px-3.5 py-1.5 text-[11px] text-fg-4">
          <span>↑↓ {s.navigate}</span>
          <span>↵ {s.insert}</span>
          <span>Esc</span>
        </div>
      </div>
      {focused && previewLeft && (
        <Preview item={focused} left={left + 392} top={top} />
      )}
    </div>
  );
}

/** Tarjeta junto al menú: qué hace el nodo elegido y qué entra y sale por sus puertos. */
function Preview({ item, left, top }: { item: Item; left: number; top: number }) {
  const { t } = useI18n();
  const s = t.spaces;
  const ins = item.model?.inputs ?? [];
  const out = item.model ? (item.model.output === "unknown" ? null : (item.model.output as PortKind)) : null;
  const Icon = item.icon;
  const chip = (k: PortKind) => (
    <span key={k} className="flex items-center gap-1 rounded-md bg-surface-3 px-1.5 py-0.5 text-[11px] text-fg-2">
      <span className="size-2 rounded-full" style={{ background: KIND_COLOR[k] }} />
      {s.listKinds[k]}
    </span>
  );
  return (
    <div
      className="pointer-events-none absolute w-[250px] rounded-2xl border border-line-2 bg-surface-2 p-4 shadow-2xl"
      style={{ left, top }}
      onClick={(e) => e.stopPropagation()}
    >
      <span className="flex size-10 items-center justify-center rounded-xl bg-surface-4">
        <Icon className="size-5 text-fg-2" />
      </span>
      <p className="mt-3 text-[15px] font-semibold">{item.title}</p>
      {item.hint && <p className="mt-1 text-[12px] leading-snug text-fg-3">{item.hint}</p>}
      {item.model && (
        <>
          {ins.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[11px] font-semibold tracking-wide text-fg-4 uppercase">{s.previewIn}</p>
              <div className="flex flex-wrap gap-1">{ins.map(chip)}</div>
            </div>
          )}
          {out && (
            <div className="mt-2">
              <p className="mb-1 text-[11px] font-semibold tracking-wide text-fg-4 uppercase">{s.previewOut}</p>
              <div className="flex flex-wrap gap-1">{chip(out)}</div>
            </div>
          )}
          <p className="mt-3 truncate font-mono text-[10px] text-fg-4">{item.model.id}</p>
        </>
      )}
    </div>
  );
}
