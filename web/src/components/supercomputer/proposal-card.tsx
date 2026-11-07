"use client";

import clsx from "clsx";
import { AlertTriangle, Check, Copy, ExternalLink, Film, ImageIcon, Loader2, Maximize2, Sparkles } from "lucide-react";
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useEffectEvent, useRef, useState } from "react";
import { FinalizeDraft } from "@/components/generations/finalize-draft";
import { ApprovalActions, providerTitle, StatusPill } from "@/components/generations/generation-card";
import { useI18n } from "@/components/i18n-provider";
import { Lightbox, type Viewable } from "@/components/lightbox";
import { costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { costShort, formatUsd, modelLabel, outputSrc, studio, StudioError, type ChatProposal, type Estimate } from "@/lib/studio";
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

/** Una pieza de una propuesta con varias: título, precio y su prompt plegado. */
function Piece({ n, title, prompt, price }: { n: number; title: string; prompt: string; price: string | null }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl bg-surface-3 px-3 py-2">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <span className="font-mono text-xs text-fg-4">{n}</span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-fg">{title}</span>
        {price && <span className="text-xs text-fg-3">{price}</span>}
      </button>
      {prompt && (
        <p className={clsx("mt-1 text-[12.5px] leading-relaxed whitespace-pre-wrap text-fg-3", !open && "line-clamp-2")}>{prompt}</p>
      )}
    </li>
  );
}

/** Sigue una generación hasta que termina (la API espera hasta 20 s por lectura) y avisa de cada cambio. */
function useJob(jobId: string, onUpdate: (g: Generation) => void) {
  useEffect(() => {
    let alive = true;
    (async () => {
      while (alive) {
        try {
          const g = await studio.get(jobId, 20);
          if (!alive) return;
          onUpdate(g);
          if (g.terminal) return;
        } catch {
          await new Promise((r) => setTimeout(r, 4000));
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [jobId, onUpdate]);
}

/** Una casilla de la cuadrícula: cargando hasta que su generación termina; luego el resultado, ampliable. */
function Tile({
  jobId,
  job,
  label,
  aspect,
  video,
  onUpdate,
  onOpen,
}: {
  jobId: string;
  job: Generation | undefined;
  label: string;
  aspect: string;
  video: boolean;
  onUpdate: (g: Generation) => void;
  onOpen: () => void;
}) {
  const { t } = useI18n();
  useJob(jobId, onUpdate);
  const out = job?.status === "completed" ? job.outputs.find((o) => o.kind === "video" || o.kind === "image") : undefined;
  return (
    <div className="space-y-1.5">
      <div className="group/out relative overflow-hidden rounded-xl bg-surface-3" style={{ aspectRatio: aspect }}>
        {out ? (
          <>
            {out.kind === "video" ? (
              <video src={outputSrc(out)} controls playsInline className="size-full bg-black object-contain" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={outputSrc(out)} alt={label} onClick={onOpen} className="size-full cursor-zoom-in object-cover" />
            )}
            <button
              type="button"
              aria-label={t.supercomputer.enlarge}
              title={t.supercomputer.enlarge}
              onClick={onOpen}
              className="absolute top-2 right-2 rounded-lg bg-black/60 p-1.5 text-white opacity-0 transition-opacity group-hover/out:opacity-100 hover:bg-black/80 focus-visible:opacity-100"
            >
              <Maximize2 className="size-4" />
            </button>
          </>
        ) : job?.terminal ? (
          <div className="flex size-full flex-col items-center justify-center gap-1.5 p-3 text-center text-xs text-danger">
            <AlertTriangle className="size-5" />
            <span className="line-clamp-3">{job.error || job.status}</span>
          </div>
        ) : (
          <div className="shimmer flex size-full flex-col items-center justify-center gap-2 text-fg-3">
            {video ? <Film className="size-5" /> : <ImageIcon className="size-5" />}
            <Loader2 className="size-4 animate-spin text-lime" />
          </div>
        )}
        <span className="absolute top-2 left-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-medium text-white">{label}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          {job && <StatusPill g={job} />}
          {job?.provider && <span className="truncate text-[11px] text-fg-4">{t.cost.via(providerTitle(job.provider))}</span>}
        </span>
        <Link href={`/history/${jobId}`} title={t.supercomputer.openDetail} className="text-fg-3 hover:text-fg">
          <ExternalLink className="size-3.5" />
        </Link>
      </div>
      {job?.status === "awaiting_approval" && <ApprovalActions g={job} />}
      {job && <FinalizeDraft g={job} variant="icon" />}
    </div>
  );
}

/**
 * Ajustes del chat que usan las propuestas: su proyecto (lo generado va ahí) y la generación automática. `fresh` son
 * las propuestas que llegaron en esta sesión: solo esas se lanzan solas (nunca las de un chat que se reabre).
 */
export type ChatAuto = {
  projectId: string | null;
  /** Lo que queda del tope de generación automática (null: apagada). */
  left: number | null;
  fresh: Set<string>;
  /** Lo gastado en automático según el servidor tras lanzar una propuesta. */
  onSpent: (spentUsd: number) => void;
  /** Tarjeta del turno en curso: la propuesta aún no está guardada, así que no se puede lanzar todavía. */
  draft?: boolean;
};
export const ChatAutoContext = createContext<ChatAuto>({ projectId: null, left: null, fresh: new Set(), onSpent: () => {} });

/**
 * Propuesta del agente: modelo, prompt y ajustes con su precio vigente. Con variaciones, una sola tarjeta con el
 * precio total que lanza todas las generaciones a la vez y las muestra en una cuadrícula a medida que terminan.
 * Solo el clic del usuario genera, con el precio que ve como tope (si sube, la API responde cost_changed y se
 * recotiza). Cada generación queda anotada en el chat para que el agente sepa cómo terminó.
 */
export function ProposalCard({ chatId, proposal }: { chatId: string; proposal: ChatProposal }) {
  const { t } = useI18n();
  const s = t.supercomputer;
  const auto = useContext(ChatAutoContext);
  const inputs = proposal.inputs?.length ? proposal.inputs : [proposal.input];
  const count = inputs.length;
  const labels = proposal.labels ?? [];
  const pieces = labels.length === count; // piezas distintas, cada una con su prompt y su precio
  // Precio vigente de cada generación: en piezas, una cotización por pieza; en variaciones, la de la primera.
  const [estimates, setEstimates] = useState<Estimate[] | null>(null);
  const estimate = estimates?.[0] ?? null;
  const [quoting, setQuoting] = useState(true);
  const [jobIds, setJobIds] = useState<string[]>(proposal.job_ids?.length ? proposal.job_ids : proposal.job_id ? [proposal.job_id] : []);
  const [jobs, setJobs] = useState<Record<string, Generation>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [viewing, setViewing] = useState<number | null>(null);
  const key = useRef<string>("");

  const prompt = typeof proposal.input.prompt === "string" ? proposal.input.prompt : "";
  const settings = Object.entries(proposal.input).filter(([k]) => k !== "prompt" && !(count > 1 && k === "seed"));
  const { name } = modelLabel(proposal.model_title);
  const ratio = typeof proposal.input.aspect_ratio === "string" && /^\d+:\d+$/.test(proposal.input.aspect_ratio) ? proposal.input.aspect_ratio.replace(":", " / ") : proposal.output === "video" ? "16 / 9" : "1 / 1";
  const pending = count - jobIds.length;

  const onUpdate = useCallback((g: Generation) => setJobs((prev) => ({ ...prev, [g.id]: g })), []);

  async function quote() {
    setQuoting(true);
    try {
      const one = pieces ? inputs : [inputs[0]];
      setEstimates(await Promise.all(one.map((input) => studio.estimate(proposal.model, input))));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setQuoting(false);
    }
  }

  // Precio vigente de una generación al abrir la tarjeta (el total es ese precio por el número de variaciones).
  useEffect(() => {
    if (proposal.job_ids?.length === count || (count === 1 && proposal.job_id)) return;
    const all = proposal.inputs?.length ? proposal.inputs : [proposal.input];
    const one = (proposal.labels?.length ?? 0) === all.length ? all : [all[0]];
    Promise.all(one.map((input) => studio.estimate(proposal.model, input)))
      .then(
        (e) => setEstimates(e),
        (e) => setError(e instanceof Error ? e.message : String(e)),
      )
      .finally(() => setQuoting(false));
  }, [proposal, count]);

  const priceOf = (i: number) => (pieces ? estimates?.[i] : estimate) ?? null;

  async function generate() {
    if (!estimates?.length || auto.draft) return;
    const known = estimates.every((e) => costAllowsDirectSubmit(e));
    if (!known && !window.confirm(s.confirmUnknown)) return;
    setBusy(true);
    setError(null);
    key.current ||= crypto.randomUUID();
    try {
      // Las que faltan, en orden; cada una con su propia clave (un reintento no duplica ninguna).
      for (let i = jobIds.length; i < count; i++) {
        const g = await studio.generate(
          proposal.model,
          inputs[i],
          `${key.current}-${i}`,
          false,
          known ? (priceOf(i)?.usd ?? null) : null,
          {},
          priceOf(i)?.reserve_usd ?? null,
          !known,
          count > 1,
          auto.projectId,
        );
        onUpdate(g);
        setJobIds((prev) => (prev.includes(g.id) ? prev : [...prev, g.id]));
        // Sin anotarla, el agente no sabría cómo terminó: se avisa en vez de callarlo.
        await studio.linkProposal(chatId, proposal.tool_use_id, g.id).catch(() => setError(s.linkFailed));
      }
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

  // Generación automática: una propuesta de esta sesión, ya guardada, cuyo total conocido parece caber en lo que queda
  // se pide al servidor, que cotiza, reserva el tope y la lanza (o la rechaza) de forma atómica e idempotente.
  async function runAuto() {
    setBusy(true);
    setError(null);
    try {
      const r = await studio.autoProposal(chatId, proposal.tool_use_id);
      setJobIds(r.proposal.job_ids ?? []);
      auto.onSpent(r.auto_spent_usd);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const launchAuto = useEffectEvent(() => void runAuto());
  useEffect(() => {
    if (auto.draft || !estimates?.length || jobIds.length || auto.left == null || !auto.fresh.has(proposal.tool_use_id)) return;
    if (!estimates.every((e) => costAllowsDirectSubmit(e))) return;
    const each = Array.from({ length: count }, (_, i) => (pieces ? estimates[i] : estimates[0])?.usd ?? null);
    if (each.some((u) => u == null)) return;
    const sum = each.reduce((a, b) => (a ?? 0) + (b ?? 0), 0) ?? 0;
    if (sum > auto.left + 1e-9) return;
    // Fuera del render del efecto: si el efecto se repite antes, se cancela y se vuelve a programar.
    const timer = setTimeout(() => {
      if (!auto.fresh.delete(proposal.tool_use_id)) return;
      launchAuto();
    }, 0);
    return () => clearTimeout(timer);
  }, [estimates, jobIds.length, auto, proposal.tool_use_id, count, pieces]);

  const unitText = costShort(estimate);
  const usds = Array.from({ length: count }, (_, i) => priceOf(i)?.usd ?? null);
  const total = usds.every((u) => u != null) ? usds.reduce((a, b) => (a ?? 0) + (b ?? 0), 0) : null;
  const sameUnit = !pieces || new Set(usds).size === 1;
  const price =
    count > 1 && total != null ? (sameUnit && unitText ? s.totalPrice(count, unitText, formatUsd(total)) : formatUsd(total)) : unitText;
  const buttonPrice = count > 1 && total != null ? formatUsd(total) : unitText;
  const done = jobIds.filter((id) => jobs[id]?.terminal).length;
  // Por dónde va a salir: el proveedor más barato con clave (el router lo elige igual al generar).
  const chosen = estimate?.options?.find((o) => o.provider === estimate.provider) ?? estimate?.options?.[0];
  const others = (estimate?.options?.length ?? 0) - 1;
  const viewable: Viewable[] = jobIds
    .map((id) => jobs[id]?.status === "completed" ? jobs[id].outputs.find((o) => o.kind === "video" || o.kind === "image") : undefined)
    .filter((o) => o !== undefined)
    .map((o) => ({ src: outputSrc(o), kind: o.kind === "video" ? "video" : "image" }));

  function openJob(id: string) {
    const g = jobs[id];
    const out = g?.outputs.find((o) => o.kind === "video" || o.kind === "image");
    const at = out ? viewable.findIndex((v) => v.src === outputSrc(out)) : -1;
    if (at >= 0) setViewing(at);
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line-2 bg-surface-2">
      <div className="flex items-center gap-3 border-b border-line px-4 py-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-lime/15 text-lime">
          {proposal.output === "video" ? <Film className="size-4" /> : <ImageIcon className="size-4" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold text-fg">{proposal.title || s.proposal}</p>
          <p className="truncate text-xs text-fg-3">
            {name}
            {count > 1 && <span className="text-lime"> · {s.variations(count)}</span>}
          </p>
        </div>
        {count === 1 && jobIds[0] && jobs[jobIds[0]] && <StatusPill g={jobs[jobIds[0]]} />}
      </div>

      <div className="space-y-3 px-4 py-3">
        {pieces && (
          <ol className="space-y-1.5">
            {inputs.map((input, i) => (
              <Piece key={i} n={i + 1} title={labels[i]} prompt={typeof input.prompt === "string" ? input.prompt : ""} price={costShort(priceOf(i))} />
            ))}
          </ol>
        )}
        {prompt && !pieces && (
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

        {jobIds.length > 0 && (
          <div className={clsx("grid gap-3", count === 1 ? "grid-cols-1" : count === 2 || count === 4 ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3")}>
            {jobIds.map((id, i) => (
              <Tile
                key={id}
                jobId={id}
                job={jobs[id]}
                label={pieces ? `${i + 1}. ${labels[i]}` : count > 1 ? `${i + 1}/${count}` : s.variation(1)}
                aspect={ratio}
                video={proposal.output === "video"}
                onUpdate={onUpdate}
                onOpen={() => openJob(id)}
              />
            ))}
          </div>
        )}
        {viewing !== null && viewable[viewing] && <Lightbox items={viewable} start={viewing} onClose={() => setViewing(null)} />}
        {pending > 0 && chosen && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl bg-surface-3 px-3 py-2 text-xs text-fg-3">
            <span className="font-medium text-fg-2">{t.cost.via(providerTitle(chosen.provider))}</span>
            <span className="font-mono text-fg-4">{chosen.model}</span>
            {!chosen.official && <span className="text-warning">{t.cost.unofficial}</span>}
            {estimate?.savings_vs_higgsfield && estimate.savings_vs_higgsfield.usd > 0 && (
              <span className="text-lime">{t.cost.saves(formatUsd(estimate.savings_vs_higgsfield.usd * (pieces ? 1 : count)), estimate.savings_vs_higgsfield.pct)}</span>
            )}
            {others > 0 && <span>{s.otherProviders(others)}</span>}
            {estimate?.reserve_usd ? <span className="basis-full">{t.cost.reserve(formatUsd(estimate.reserve_usd * (pieces ? 1 : count)))}</span> : null}
          </div>
        )}
        {error && <p className="text-sm text-warning">{error}</p>}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3">
        {jobIds.length > 0 ? (
          count > 1 ? (
            <span className="text-sm text-fg-3">{s.progress(done, count)}</span>
          ) : (
            <Link href={`/history/${jobIds[0]}`} className="flex items-center gap-1.5 text-sm text-fg-3 hover:text-fg">
              <ExternalLink className="size-3.5" /> {s.openDetail}
            </Link>
          )
        ) : (
          <span className="text-sm text-fg-3">{quoting ? <Loader2 className="size-4 animate-spin" /> : (price ?? t.cost.unavailable)}</span>
        )}
        {pending > 0 ? (
          <button
            type="button"
            onClick={() => void generate()}
            disabled={busy || quoting || !estimate || auto.draft}
            title={auto.draft ? s.waitTurn : undefined}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink transition hover:brightness-105 disabled:opacity-50"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {jobIds.length > 0 ? s.launchRest(pending) : s.generate}
            {buttonPrice && jobIds.length === 0 && <span className="font-normal opacity-80">· {buttonPrice}</span>}
          </button>
        ) : (
          done < count && (
            <span className="flex items-center gap-1.5 text-sm text-lime">
              <Loader2 className="size-4 animate-spin" /> {s.generating}
            </span>
          )
        )}
      </div>
    </div>
  );
}
