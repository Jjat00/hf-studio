"use client";

import clsx from "clsx";
import { ArrowRight, Bot, Check, Copy, Lightbulb, MonitorPlay, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { formatUsd, studio, type Estimate } from "@/lib/studio";
import type { Channel, Step, UseCase } from "@/lib/use-cases";

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="flex h-7 items-center gap-1.5 rounded-lg bg-glass px-2.5 text-xs font-medium text-fg-2 hover:text-fg"
    >
      {done ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
      {done ? "Copied" : label}
    </button>
  );
}

/** Costo orientativo del ejemplo: el definitivo se muestra en el estudio o lo cotiza el agente antes de generar. */
function CostHint({ useCase }: { useCase: UseCase }) {
  const [state, setState] = useState<{ value: Estimate | null; failed: boolean }>({ value: null, failed: false });
  useEffect(() => {
    let alive = true;
    studio
      .estimate(useCase.model, useCase.sample)
      .then((value) => alive && setState({ value, failed: false }))
      .catch(() => alive && setState({ value: null, failed: true }));
    return () => {
      alive = false;
    };
  }, [useCase]);
  const e = state.value;
  let text = "Checking price…";
  let note = useCase.costNote;
  if (state.failed) text = "Price not available here";
  else if (e?.kind === "exact" && e.credits !== null) text = `${+e.credits.toFixed(3)} credits${e.usd !== null ? ` · ${formatUsd(e.usd)}` : ""}`;
  else if (e?.kind === "approx" && e.usd !== null && e.missing.length === 0) text = `~${formatUsd(e.usd)}`;
  else if (e?.usd != null) {
    // Subtotal: aún falta un dato facturable (p. ej. la duración del video de entrada).
    text = `From ~${formatUsd(e.usd)}`;
    note = `Plus the ${e.missing.join(", ")}. The studio tries to complete the price once your media is added; if it can't, it asks you to confirm an unknown cost.`;
  } else if (e) text = "Priced once your media is added";
  if (state.failed || (e && e.usd == null))
    note ??= "The studio shows the price before generating; if it can't, it asks you to confirm an unknown cost.";
  return (
    <div className="rounded-2xl border border-line bg-surface-2 px-4 py-3">
      <p className="text-[13px] text-fg-3">Example cost</p>
      <p className="mt-0.5 text-[15px] font-semibold">{text}</p>
      {note && <p className="mt-1 text-[12px] leading-snug text-fg-3">{note}</p>}
      <p className="mt-0.5 truncate font-mono text-[11px] text-fg-4" title={useCase.model}>
        {useCase.model}
      </p>
    </div>
  );
}

function Steps({ steps }: { steps: Step[] }) {
  return (
    <ol className="relative flex flex-col gap-5">
      {steps.map((s, i) => (
        <li key={i} className="flex gap-4">
          <div className="flex flex-col items-center">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-lime text-sm font-bold text-ink">{i + 1}</span>
            {i < steps.length - 1 && <span className="mt-1 w-px flex-1 bg-line-2" />}
          </div>
          <div className="min-w-0 pb-1">
            <p className="text-[12px] font-semibold tracking-wider text-fg-3 uppercase">Step {i + 1}</p>
            <p className="mt-0.5 text-[16px] font-semibold">{s.title}</p>
            {s.body && <p className="mt-1 text-[15px] leading-snug text-fg-2">{s.body}</p>}
            {s.tool && (
              <p className="mt-2 inline-block rounded-lg bg-lime/10 px-2 py-1 font-mono text-[12px] text-lime">{s.tool}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Mini tutorial de un caso de uso: pasos en la UI o con el MCP, prompts de ejemplo y consejos. */
export function UseCasePanel({ useCase: u, onClose }: { useCase: UseCase; onClose: () => void }) {
  const [channel, setChannel] = useState<Channel>(u.channels[0]);
  const close = useEffectEvent(onClose);
  const panel = useRef<HTMLElement>(null);
  // Diálogo modal: foco dentro, Tab atrapado, Escape cierra; al salir se devuelven foco y scroll.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return close();
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled])")];
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      if (e.shiftKey && (document.activeElement === first || !panel.current.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !panel.current.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, []);
  const tryHref = (prompt?: string) => (u.uiHref ? `${u.uiHref}${prompt ? `&${new URLSearchParams({ prompt })}` : ""}` : undefined);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={u.title}>
      <button type="button" tabIndex={-1} aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <aside ref={panel} className="thin-scrollbar relative flex h-full w-full max-w-[720px] flex-col overflow-y-auto bg-surface-1 shadow-2xl">
        <div className="grain relative aspect-[16/8] shrink-0 overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={u.art} alt="" className="absolute inset-0 size-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-surface-1 via-black/20 to-transparent" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            data-autofocus
            className="absolute top-4 right-4 flex size-9 items-center justify-center rounded-xl bg-black/60 text-fg backdrop-blur hover:bg-black/80"
          >
            <X className="size-4" />
          </button>
          <div className="absolute inset-x-0 bottom-0 px-6 pb-4 md:px-8">
            <p className="text-[13px] font-semibold tracking-wider text-lime uppercase">{u.category}</p>
            <h2 className="headline mt-1 text-[30px] md:text-[40px]">{u.title}</h2>
          </div>
        </div>

        <div className="flex flex-col gap-8 px-6 pt-2 pb-10 md:px-8">
          <p className="text-[16px] leading-relaxed text-fg-2">{u.tagline}</p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
            <CostHint useCase={u} />
            <div className="flex gap-2 sm:flex-col">
              {u.uiHref && (
                <Link
                  href={tryHref(u.prompts.find((p) => p.text)?.text)!}
                  className="flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl bg-lime px-4 text-sm font-semibold text-ink"
                >
                  Try it in the studio <ArrowRight className="size-4" />
                </Link>
              )}
              {u.preset && (
                <Link
                  href={`/presets/${u.preset}`}
                  className="flex h-11 flex-1 items-center justify-center rounded-xl bg-surface-4 px-4 text-sm font-medium text-fg-2 hover:text-fg"
                >
                  Open preset /{u.preset}
                </Link>
              )}
            </div>
          </div>

          <section>
            {u.channels.length > 1 ? (
              <div className="flex gap-1 rounded-xl bg-surface-2 p-1">
                {u.channels.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setChannel(c)}
                    className={clsx(
                      "flex h-9 flex-1 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors",
                      channel === c ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg",
                    )}
                  >
                    {c === "ui" ? <MonitorPlay className="size-4" /> : <Bot className="size-4" />}
                    {c === "ui" ? "In the UI" : "With Claude Code / Codex"}
                  </button>
                ))}
              </div>
            ) : (
              <p className="flex items-center gap-2 text-sm font-medium text-fg-2">
                <Bot className="size-4 text-lime" /> Agents only: ask Claude Code or Codex through the HF Studio MCP
              </p>
            )}

            <div className="mt-6">
              {channel === "ui" && u.ui ? (
                <Steps steps={u.ui} />
              ) : (
                <div className="flex flex-col gap-6">
                  <div className="rounded-2xl border border-lime/25 bg-lime/5 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[13px] font-semibold text-lime">Ask your agent</p>
                      <CopyButton text={u.ask} />
                    </div>
                    <p className="mt-2 text-[15px] leading-relaxed text-fg">“{u.ask}”</p>
                  </div>
                  <Steps steps={u.mcp} />
                  <p className="text-[13px] leading-snug text-fg-3">
                    The agent quotes first and waits for your OK: HF Studio only generates with the quote_id of that exact quote,
                    and without a complete price it also needs you to explicitly accept an unknown cost. Setup on the{" "}
                    <Link href="/mcp" className="text-lime hover:underline">
                      MCP page
                    </Link>
                    .
                  </p>
                </div>
              )}
            </div>
          </section>

          <section>
            <h3 className="headline text-[22px]">Example prompts</h3>
            <div className="mt-4 flex flex-col gap-3">
              {u.prompts.map((p) => (
                <div key={p.label} className="rounded-2xl border border-line bg-surface-2 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold">{p.label}</p>
                    <div className="flex gap-1.5">
                      {p.text && <CopyButton text={p.text} />}
                      {p.text && u.uiHref && (
                        <Link
                          href={tryHref(p.text)!}
                          className="flex h-7 items-center gap-1 rounded-lg bg-lime/10 px-2.5 text-xs font-medium text-lime hover:bg-lime/20"
                        >
                          Use in studio <ArrowRight className="size-3.5" />
                        </Link>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 font-mono text-[13px] leading-relaxed text-fg-2">
                    {p.text || "Leave the prompt empty: the character image and the motion clip are enough."}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl bg-surface-2 p-5">
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Lightbulb className="size-4 text-warning" /> Tips
            </p>
            <ul className="mt-3 flex flex-col gap-2 text-[15px] leading-snug text-fg-2">
              {u.tips.map((t) => (
                <li key={t}>· {t}</li>
              ))}
            </ul>
          </section>
        </div>
      </aside>
    </div>
  );
}
