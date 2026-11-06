"use client";

import clsx from "clsx";
import { Check, Copy, ExternalLink, Film, ImageIcon, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApprovalActions, StatusPill } from "@/components/generations/generation-card";
import { useI18n } from "@/components/i18n-provider";
import { costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { costShort, modelLabel, outputSrc, studio, StudioError, type ChatProposal, type Estimate } from "@/lib/studio";
import type { Generation } from "@/lib/types";

/** Valor corto de un ajuste: las URLs se muestran por su nombre de archivo. */
function short(value: unknown): string {
  if (Array.isArray(value)) return value.map(short).join(", ");
  if (typeof value === "string" && value.startsWith("http")) return value.split("/").pop()?.slice(0, 28) ?? value;
  if (value && typeof value === "object") return JSON.stringify(value).slice(0, 40);
  return String(value);
}

function CopyButton({ text }: { text: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="flex items-center gap-1 text-xs text-fg-3 hover:text-fg"
    >
      {done ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
      {done ? t.copy.copied : t.copy.copy}
    </button>
  );
}

/**
 * Propuesta del agente: modelo, prompt y ajustes con su precio vigente. Solo el clic del usuario genera, con el
 * precio que ve como tope (si sube, la API responde cost_changed y se recotiza). La generación queda anotada en
 * el chat para que el agente sepa cómo terminó, y su resultado se ve aquí mismo.
 */
export function ProposalCard({ chatId, proposal }: { chatId: string; proposal: ChatProposal }) {
  const { t } = useI18n();
  const s = t.supercomputer;
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [quoting, setQuoting] = useState(true);
  const [jobId, setJobId] = useState<string | null>(proposal.job_id);
  const [job, setJob] = useState<Generation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const key = useRef<string>("");

  const prompt = typeof proposal.input.prompt === "string" ? proposal.input.prompt : "";
  const settings = Object.entries(proposal.input).filter(([k]) => k !== "prompt");
  const { name } = modelLabel(proposal.model_title);

  async function quote() {
    setQuoting(true);
    try {
      setEstimate(await studio.estimate(proposal.model, proposal.input));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setQuoting(false);
    }
  }

  // Precio vigente al abrir la tarjeta (el de la propuesta pudo cambiar desde que el agente la cotizó).
  useEffect(() => {
    if (proposal.job_id) return;
    studio.estimate(proposal.model, proposal.input).then(
      (e) => setEstimate(e),
      (e) => setError(e instanceof Error ? e.message : String(e)),
    ).finally(() => setQuoting(false));
  }, [proposal]);

  // Sigue la generación hasta que termina (la API espera hasta 20 s por lectura).
  useEffect(() => {
    if (!jobId) return;
    let alive = true;
    (async () => {
      while (alive) {
        try {
          const g = await studio.get(jobId, 20);
          if (!alive) return;
          setJob(g);
          if (g.terminal) return;
        } catch {
          await new Promise((r) => setTimeout(r, 4000));
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [jobId]);

  async function generate() {
    if (!estimate) return;
    const known = costAllowsDirectSubmit(estimate);
    if (!known && !window.confirm(s.confirmUnknown)) return;
    setBusy(true);
    setError(null);
    key.current ||= crypto.randomUUID();
    try {
      const g = await studio.generate(
        proposal.model,
        proposal.input,
        key.current,
        false,
        known ? estimate.usd : null,
        {},
        estimate.reserve_usd ?? null,
        !known,
      );
      await studio.linkProposal(chatId, proposal.tool_use_id, g.id).catch(() => {});
      setJob(g);
      setJobId(g.id);
    } catch (e) {
      if (e instanceof StudioError && (e.code === "cost_changed" || e.code === "reserve_not_approved")) {
        setError(s.priceChanged);
        key.current = "";
        void quote();
      } else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const price = costShort(estimate);
  const outputs = job?.status === "completed" ? job.outputs : [];

  return (
    <div className="overflow-hidden rounded-2xl border border-line-2 bg-surface-2">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-lime/15 text-lime">
          {proposal.output === "video" ? <Film className="size-4" /> : <ImageIcon className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold text-fg">{proposal.title || s.proposal}</p>
          <p className="truncate text-xs text-fg-3">{name}</p>
        </div>
        {job && <StatusPill g={job} />}
      </div>

      <div className="space-y-3 px-4 py-3">
        {prompt && (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{s.prompt}</span>
              <CopyButton text={prompt} />
            </div>
            <p className={clsx("text-[13.5px] leading-relaxed whitespace-pre-wrap text-fg-2", !open && "line-clamp-6")}>{prompt}</p>
            {prompt.length > 420 && (
              <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-xs font-medium text-lime hover:underline">
                {open ? s.showLess : s.showMore}
              </button>
            )}
          </div>
        )}
        {settings.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {settings.map(([k, v]) => (
              <span key={k} className="rounded-md bg-surface-4 px-2 py-0.5 text-xs text-fg-2">
                <span className="text-fg-4">{k}</span> {short(v)}
              </span>
            ))}
          </div>
        )}

        {outputs.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {outputs.map((o, i) =>
              o.kind === "video" ? (
                <video key={i} src={outputSrc(o)} controls playsInline className="w-full rounded-xl bg-black" />
              ) : o.kind === "image" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={i} src={outputSrc(o)} alt={proposal.title} className="w-full rounded-xl" />
              ) : null,
            )}
          </div>
        )}
        {job?.status === "awaiting_approval" && <ApprovalActions g={job} />}
        {job?.terminal && job.status !== "completed" && job.error && <p className="text-sm text-danger">{job.error}</p>}
        {error && <p className="text-sm text-warning">{error}</p>}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3">
        {jobId ? (
          <Link href={`/history/${jobId}`} className="flex items-center gap-1.5 text-sm text-fg-3 hover:text-fg">
            <ExternalLink className="size-3.5" /> {s.openDetail}
          </Link>
        ) : (
          <span className="text-sm text-fg-3">{quoting ? <Loader2 className="size-4 animate-spin" /> : (price ?? t.cost.unavailable)}</span>
        )}
        {!jobId ? (
          <button
            type="button"
            onClick={generate}
            disabled={busy || quoting || !estimate}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink transition hover:brightness-105 disabled:opacity-50"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {s.generate}
            {price && <span className="font-normal opacity-80">· {price}</span>}
          </button>
        ) : (
          !job?.terminal && (
            <span className="flex items-center gap-1.5 text-sm text-lime">
              <Loader2 className="size-4 animate-spin" /> {s.generating}
            </span>
          )
        )}
      </div>
    </div>
  );
}
