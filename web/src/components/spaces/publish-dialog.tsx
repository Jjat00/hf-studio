"use client";

import { Loader2, X } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import type { Flow, SpaceNode } from "@/lib/spaces";

/** Publicar el lienzo como flujo: título, descripción y qué nodos de texto, medio o lista son entradas. */
export function PublishDialog({
  initial,
  nodes,
  name,
  busy,
  error,
  onSave,
  onClose,
}: {
  initial: Flow;
  nodes: SpaceNode[];
  name: (n: SpaceNode) => string;
  busy: boolean;
  error: string | null;
  onSave: (flow: Flow | null) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const s = t.spaces;
  const candidates = nodes.filter((n) => n.type === "text" || n.type === "media" || n.type === "list");
  const [title, setTitle] = useState(initial.title);
  const [description, setDescription] = useState(initial.description);
  const [labels, setLabels] = useState<Record<string, string>>(() =>
    Object.fromEntries(initial.inputs.map((i) => [i.node_id, i.label])),
  );
  const chosen = candidates.filter((n) => labels[n.id] !== undefined);
  const valid = title.trim() && chosen.length > 0 && chosen.every((n) => labels[n.id]?.trim());

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-panel border border-line bg-surface-1" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <p className="font-semibold">{s.publishTitle}</p>
          <button type="button" aria-label={s.close} onClick={onClose} className="text-fg-3 hover:text-fg">
            <X className="size-5" />
          </button>
        </div>
        <div className="thin-scrollbar flex flex-col gap-3 overflow-y-auto p-5">
          <p className="text-sm text-fg-2">{s.publishIntro}</p>
          <label className="flex flex-col gap-1 text-[13px] text-fg-3">
            {s.flowName}
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} className="rounded-xl bg-surface-3 px-3 py-2 text-[15px] text-fg outline-none" />
          </label>
          <label className="flex flex-col gap-1 text-[13px] text-fg-3">
            {s.flowDescription}
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} rows={2} className="resize-none rounded-xl bg-surface-3 px-3 py-2 text-[14px] text-fg outline-none" />
          </label>
          <p className="pt-1 text-[13px] font-semibold text-fg-2">{s.flowInputs}</p>
          {candidates.length === 0 && <p className="text-sm text-fg-3">{s.flowNoCandidates}</p>}
          {candidates.map((n) => {
            const on = labels[n.id] !== undefined;
            return (
              <div key={n.id} className="flex flex-col gap-1.5 rounded-xl border border-line bg-surface-2 p-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={(e) =>
                      setLabels((prev) => {
                        const next = { ...prev };
                        if (e.target.checked) next[n.id] = name(n);
                        else delete next[n.id];
                        return next;
                      })
                    }
                    className="accent-lime"
                  />
                  <span className="truncate">{name(n)}</span>
                </label>
                {on && (
                  <input
                    value={labels[n.id]}
                    onChange={(e) => setLabels((prev) => ({ ...prev, [n.id]: e.target.value }))}
                    maxLength={80}
                    placeholder={s.flowLabel}
                    className="rounded-lg bg-surface-4 px-2.5 py-1.5 text-[13px] outline-none"
                  />
                )}
              </div>
            );
          })}
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
        <div className="flex justify-between gap-2 border-t border-line p-4">
          <button type="button" disabled={busy || initial.inputs.length === 0} onClick={() => onSave(null)} className="rounded-xl px-3 py-2 text-sm text-fg-3 hover:text-danger disabled:opacity-0">
            {s.flowUnpublish}
          </button>
          <button
            type="button"
            disabled={!valid || busy}
            onClick={() => onSave({ title: title.trim(), description: description.trim(), inputs: chosen.map((n) => ({ node_id: n.id, label: labels[n.id].trim() })) })}
            className="flex items-center gap-2 rounded-xl bg-lime px-4 py-2 text-sm font-semibold text-ink disabled:opacity-50"
          >
            {busy && <Loader2 className="size-4 animate-spin" />}
            {s.flowSave}
          </button>
        </div>
      </div>
    </div>
  );
}
