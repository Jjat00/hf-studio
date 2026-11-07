"use client";

import { AtSign, Check, Film, Loader2 } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio, type ChatProposal } from "@/lib/studio";

/**
 * Tarjeta de `create_element_from_generation`: AI Director propone guardar unas salidas como elemento. Los elementos
 * se comparten en toda la instalación, así que solo se crea con este clic del usuario.
 */
export function ElementProposalCard({ chatId, proposal }: { chatId: string; proposal: ChatProposal }) {
  const { t } = useI18n();
  const p = t.production;
  const [created, setCreated] = useState<string | null>(proposal.element_id ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const el = await studio.createProposedElement(chatId, proposal.tool_use_id);
      setCreated(el.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-2xl border border-line-2 bg-surface-2 p-4">
      <p className="flex items-center gap-2 text-xs font-semibold tracking-wider text-fg-4 uppercase">
        <AtSign className="size-3.5" /> {p.elementCard}
      </p>
      <p className="mt-1 text-[15px] font-semibold text-fg">@{proposal.name}</p>
      {proposal.description && <p className="mt-1 text-sm text-fg-3">{proposal.description}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {(proposal.previews ?? []).map((v, i) => (
          <span key={i} className="relative h-20 w-20 overflow-hidden rounded-lg bg-surface-4" title={v.frame ? p.frame(v.frame) : undefined}>
            {v.kind === "video" ? (
              <video src={v.url} className="size-full object-cover" muted playsInline preload="metadata" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={v.url} alt="" className="size-full object-cover" />
            )}
            {v.kind === "video" && <Film className="absolute right-1 bottom-1 size-3.5 text-white drop-shadow" />}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-fg-4">{p.elementHint}</p>
      {created ? (
        <p className="mt-3 flex items-center gap-1.5 text-sm font-medium text-lime">
          <Check className="size-4" /> {p.elementCreated(proposal.name ?? "")}
        </p>
      ) : (
        <button
          type="button"
          onClick={() => void create()}
          disabled={busy}
          className="mt-3 flex h-9 items-center gap-1.5 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-50"
        >
          {busy && <Loader2 className="size-4 animate-spin" />}
          {p.createElement}
        </button>
      )}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </div>
  );
}
