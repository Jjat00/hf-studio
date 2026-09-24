"use client";

import clsx from "clsx";
import { Check, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { workflowLabel } from "@/lib/i18n/workflow";
import { modelLabel } from "@/lib/studio";
import type { ModelSummary } from "@/lib/types";

export function ModelRow({ model, onClick }: { model?: ModelSummary; onClick: () => void }) {
  const { t, locale } = useI18n();
  const { name, workflow } = model ? modelLabel(model.title) : { name: t.picker.chooseModel, workflow: "" };
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface-3 px-4 py-3 text-left transition-colors hover:bg-surface-4"
    >
      <span className="min-w-0">
        <span className="block text-[13px] text-fg-3">{t.picker.model}</span>
        <span className="flex items-center gap-2 truncate text-[16px] font-semibold">
          {name}
          {workflow && <span className="truncate text-sm font-normal text-fg-3">{workflowLabel(workflow, locale)}</span>}
        </span>
      </span>
      <ChevronRight className="size-5 shrink-0 text-fg-3" />
    </button>
  );
}

export function ModelPicker({
  open,
  models,
  selected,
  onSelect,
  onClose,
}: {
  open: boolean;
  models: ModelSummary[];
  selected?: string;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const CAP_LABEL = t.picker.caps;
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open, onClose]);

  const groups = useMemo(() => {
    const term = q.toLowerCase();
    const list = models.filter((m) => !term || m.id.includes(term) || m.title.toLowerCase().includes(term));
    const map = new Map<string, ModelSummary[]>();
    for (const m of list) {
      const name = modelLabel(m.title).name;
      map.set(name, [...(map.get(name) ?? []), m]);
    }
    return [...map.entries()];
  }, [models, q]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 p-4 pt-[10vh] backdrop-blur-sm" onClick={onClose}>
      <div
        className="flex max-h-[75vh] w-full max-w-xl flex-col overflow-hidden rounded-panel border border-line bg-surface-2 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <Search className="size-4 text-fg-3" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t.picker.search}
            className="flex-1 bg-transparent text-[15px] outline-none placeholder:text-fg-3"
          />
          <button type="button" onClick={onClose} aria-label={t.picker.close} className="text-fg-3 hover:text-fg">
            <X className="size-5" />
          </button>
        </div>
        <div className="thin-scrollbar overflow-y-auto p-2">
          {groups.length === 0 && <p className="p-6 text-center text-sm text-fg-3">{t.picker.noResults}</p>}
          {groups.map(([family, list]) => (
            <div key={family} className="mb-1">
              <p className="px-3 pt-3 pb-1 text-xs font-semibold tracking-wide text-fg-3 uppercase">{family}</p>
              {list.map((m) => {
                const active = m.id === selected;
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      onSelect(m.id);
                      onClose();
                    }}
                    className={clsx(
                      "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors",
                      active ? "bg-lime/10" : "hover:bg-glass",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-semibold">
                        {workflowLabel(modelLabel(m.title).workflow || m.workflow, locale)}
                      </span>
                      <span className="block truncate font-mono text-[11px] text-fg-3">{m.id}</span>
                    </span>
                    <span className="hidden gap-1 sm:flex">
                      {m.capabilities
                        .filter((c) => CAP_LABEL[c])
                        .slice(0, 3)
                        .map((c) => (
                          <span key={c} className="rounded-md bg-glass px-1.5 py-0.5 text-[11px] text-fg-2">
                            {CAP_LABEL[c]}
                          </span>
                        ))}
                    </span>
                    {active && <Check className="size-4 text-lime" />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
