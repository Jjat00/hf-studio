"use client";

import clsx from "clsx";
import { AlertTriangle, AudioLines, Ban, Bookmark, Check, Copy, Download, Info, Loader2, RotateCcw, ShieldAlert, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import type { Locale } from "@/lib/i18n";
import { workflowLabel } from "@/lib/i18n/workflow";
import { formatUsd, modelLabel, outputSrc, studio, VOICE_MODEL } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";

const RATIO: Record<string, string> = {
  "16:9": "16 / 9",
  "9:16": "9 / 16",
  "1:1": "1 / 1",
  "4:3": "4 / 3",
  "3:4": "3 / 4",
  "21:9": "21 / 9",
  "3:2": "3 / 2",
  "2:3": "2 / 3",
};

const ICON_BUTTON =
  "flex size-8 items-center justify-center rounded-lg bg-glass text-fg-2 transition-colors hover:bg-white/10 hover:text-fg disabled:opacity-40";

function useElapsed(g: Generation) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (g.terminal) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [g.terminal]);
  const end = g.finished_at ? Date.parse(g.finished_at) : now;
  const s = Math.max(0, Math.round((end - Date.parse(g.created_at)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

// Trabajos locales de ElevenLabs (no están en el catálogo de Higgsfield).
const LOCAL_MODELS: Record<string, Record<Locale, string>> = {
  [VOICE_MODEL]: { es: "Cambio de voz", en: "Voice change" },
  "elevenlabs/text-to-speech": { es: "Texto a voz", en: "Text to speech" },
  "elevenlabs/sound-effects": { es: "Efecto de sonido", en: "Sound effect" },
  "elevenlabs/music": { es: "Música", en: "Music" },
  "elevenlabs/voice-isolator": { es: "Voz aislada", en: "Isolated voice" },
};

/** Reproductor de un resultado de audio (texto a voz, efectos, música…). */
export function AudioPlayer({ src }: { src: string }) {
  return (
    <div className="flex w-full flex-col items-center justify-center gap-4 rounded-2xl bg-gradient-to-br from-lime/15 via-surface-3 to-pink/10 px-4 py-8">
      <AudioLines className="size-10 text-lime" />
      <audio src={src} controls preload="metadata" className="w-full" />
    </div>
  );
}

// Nombres de los proveedores (registry.py); uno nuevo se muestra con su id hasta añadirlo aquí.
export const PROVIDER_TITLES: Record<string, string> = { higgsfield: "Higgsfield", apimart: "APIMart", kie: "KIE" };

export function providerTitle(name: string | undefined) {
  return name ? (PROVIDER_TITLES[name] ?? name) : "";
}

/** Opción actual del plan: en awaiting_approval, la que espera que se apruebe su precio. */
export function currentOption(g: Generation) {
  return (g.plan ?? []).find((o) => o.provider === g.provider);
}

// Nombres legibles de los clientes habituales; cualquier otro se muestra tal cual.
const SOURCES: Record<string, string> = {
  "claude-code": "Claude Code",
  "claude-desktop": "Claude Desktop",
  codex: "Codex",
  "chatgpt-desktop": "ChatGPT",
};

export function sourceLabel(source: string | undefined, ui: string) {
  if (!source) return null;
  return source === "web-ui" ? ui : (SOURCES[source] ?? source);
}

export function modelName(id: string, locale: Locale, models?: Map<string, ModelSummary>) {
  const own = LOCAL_MODELS[id];
  if (own) return `ElevenLabs · ${own[locale]}`;
  const m = models?.get(id);
  if (!m) return id;
  const { name, workflow } = modelLabel(m.title);
  return workflow ? `${name} · ${workflowLabel(workflow, locale)}` : name;
}

export function GenerationCard({
  g,
  layout,
  models,
  onReuse,
  onDelete,
}: {
  g: Generation;
  layout: "grid" | "list";
  models?: Map<string, ModelSummary>;
  onReuse?: (g: Generation) => void;
  onDelete?: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  const STAGE = t.generation.stage;
  const elapsed = useElapsed(g);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  async function saveAsPreset() {
    const title = window.prompt(t.generation.presetName, prompt.slice(0, 40) || t.generation.myPreset);
    if (!title) return;
    const slug = title.toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "preset";
    try {
      const p = await studio.savePreset(g.id, slug, title);
      setSaved(p.slug);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e));
    }
  }
  const prompt = typeof g.input.prompt === "string" ? g.input.prompt : "";
  const source = sourceLabel(g.source, t.history.detail.webUi);
  const ratio = RATIO[String(g.input.aspect_ratio ?? "")] ?? "16 / 9";
  const main = g.outputs[0];
  const failed = ["failed", "nsfw", "timed_out", "canceled"].includes(g.status);

  const media = (
    <div
      className="relative w-full overflow-hidden rounded-2xl bg-surface-3"
      style={{ aspectRatio: g.status === "completed" && main ? undefined : ratio }}
    >
      {g.status === "completed" && main ? (
        main.kind === "audio" ? (
          <AudioPlayer src={outputSrc(main)} />
        ) : main.kind === "video" ? (
          <video src={outputSrc(main)} className="block w-full" controls loop playsInline preload="metadata" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={outputSrc(main)} alt={prompt} className="block w-full" loading="lazy" />
        )
      ) : g.status === "awaiting_approval" ? (
        <ApprovalPanel g={g} />
      ) : failed ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
          {g.status === "nsfw" ? (
            <ShieldAlert className="size-7 text-pink" />
          ) : g.status === "canceled" ? (
            <Ban className="size-7 text-fg-3" />
          ) : (
            <AlertTriangle className="size-7 text-danger" />
          )}
          <p className="text-sm font-semibold">{STAGE[g.status] ?? g.stage}</p>
          {g.error && <p className="line-clamp-3 max-w-sm text-xs text-fg-3">{g.error}</p>}
        </div>
      ) : (
        <div className="shimmer absolute inset-0 flex flex-col items-center justify-center gap-3">
          <Loader2 className="size-6 animate-spin text-lime" />
          <p className="text-sm font-semibold">{STAGE[g.status] ?? g.stage}</p>
          <p className="font-mono text-xs text-fg-3">{elapsed}</p>
        </div>
      )}
      {source && (
        <span className="absolute top-3 right-3 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold">{source}</span>
      )}
      {g.outputs.length > 1 && (
        <span className="absolute top-3 left-3 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold">
          +{g.outputs.length - 1}
        </span>
      )}
    </div>
  );

  const detailHref = `/history/${g.id}`;
  const actions = (
    <div className="flex items-center gap-1">
      <Link href={detailHref} title={t.history.detail.open} aria-label={t.history.detail.open} className={ICON_BUTTON}>
        <Info className="size-4" />
      </Link>
      {g.status === "completed" && main && (
        <IconButton label={t.generation.download} href={outputSrc(main)}>
          <Download className="size-4" />
        </IconButton>
      )}
      {onReuse && (
        <IconButton label={t.generation.reuse} onClick={() => onReuse(g)}>
          <RotateCcw className="size-4" />
        </IconButton>
      )}
      {prompt && (
        <IconButton label={t.generation.copyPrompt} onClick={() => navigator.clipboard.writeText(prompt)}>
          <Copy className="size-4" />
        </IconButton>
      )}
      {g.status === "completed" && !LOCAL_MODELS[g.model] && (
        <IconButton label={saved ? t.generation.savedAs(saved) : t.generation.saveAsPreset} onClick={saveAsPreset}>
          {saved ? <Check className="size-4 text-lime" /> : <Bookmark className="size-4" />}
        </IconButton>
      )}
      {onDelete && g.terminal && (
        <IconButton label={t.generation.delete} onClick={() => onDelete(g.id)}>
          <Trash2 className="size-4" />
        </IconButton>
      )}
      {(g.status === "pending" || g.status === "queued" || g.status === "awaiting_approval") && (
        <IconButton
          label={t.generation.cancel}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            await studio.cancel(g.id).catch(() => undefined);
            setBusy(false);
          }}
        >
          <X className="size-4" />
        </IconButton>
      )}
    </div>
  );

  const meta = (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-fg-3">
      <span className="rounded-md bg-glass px-1.5 py-0.5 font-medium text-fg-2">{modelName(g.model, locale, models)}</span>
      {source && <span className="rounded-md bg-lime/10 px-1.5 py-0.5 font-medium text-lime">{source}</span>}
      {g.provider && !LOCAL_MODELS[g.model] && (
        <span className="rounded-md bg-glass px-1.5 py-0.5" title={g.attempts?.length ? g.attempts.map((a) => `${providerTitle(a.provider)}: ${a.error}`).join("\n") : undefined}>
          {t.cost.via(providerTitle(g.provider))}
          {g.cost_usd != null ? ` · ${formatUsd(g.cost_usd)}` : ""}
        </span>
      )}
      {["resolution", "duration", "aspect_ratio"].map((k) =>
        g.input[k] !== undefined ? (
          <span key={k} className="rounded-md bg-glass px-1.5 py-0.5">
            {k === "duration" ? `${g.input[k]}s` : String(g.input[k])}
          </span>
        ) : null,
      )}
      <span className="ml-auto font-mono">{g.terminal ? elapsed : ""}</span>
    </div>
  );

  if (layout === "list") {
    return (
      <article className="grid grid-cols-1 gap-4 rounded-card border border-line bg-surface-2 p-3 md:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {media}
        <div className="flex min-w-0 flex-col gap-3 py-1">
          <div className="flex items-center justify-between gap-2">
            <StatusPill g={g} />
            {actions}
          </div>
          <Link
            href={detailHref}
            className={clsx("text-[15px] leading-relaxed hover:underline", prompt ? "text-fg" : "text-fg-3 italic")}
          >
            {prompt || t.generation.noPrompt}
          </Link>
          <div className="mt-auto">{meta}</div>
        </div>
      </article>
    );
  }
  return (
    <article className="group flex flex-col gap-2">
      {media}
      <div className="flex items-start justify-between gap-2 px-1">
        <Link href={detailHref} className="line-clamp-2 min-w-0 text-sm text-fg-2 hover:text-fg">
          {prompt || modelName(g.model, locale, models)}
        </Link>
        <div className="opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100">{actions}</div>
      </div>
    </article>
  );
}

/** El proveedor más barato falló sin cobrar y el siguiente cuesta más: aprobar ese precio o cancelar. */
function ApprovalPanel({ g }: { g: Generation }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const next = currentOption(g);
  const price = next?.usd != null ? `${next.kind === "approx" ? "~" : ""}${formatUsd(next.usd)}` : t.approval.unknownPrice;
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
      <AlertTriangle className="size-7 text-warning" />
      <p className="text-sm font-semibold">{t.approval.title}</p>
      {g.error && <p className="line-clamp-3 max-w-sm text-xs text-fg-3">{g.error}</p>}
      {next?.reserve_usd != null && <p className="max-w-sm text-xs text-warning">{t.cost.reserve(formatUsd(next.reserve_usd))}</p>}
      <div className="mt-1 flex gap-2">
        <button
          type="button"
          disabled={busy || !next}
          onClick={() =>
            next &&
            act(() =>
              // Sin precio, el botón dice explícitamente que se aprueba un costo desconocido (sin tope).
              next.usd != null
                ? studio.approve(g.id, next.usd, next.reserve_usd ?? null)
                : studio.approve(g.id, null, next.reserve_usd ?? null, true),
            )
          }
          className="rounded-lg bg-lime px-3 py-1.5 text-xs font-bold text-black disabled:opacity-50"
        >
          {next?.usd != null
            ? t.approval.approve(`${price} · ${providerTitle(next?.provider)}`)
            : t.approval.approveUnknown(providerTitle(next?.provider))}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => act(() => studio.cancel(g.id))}
          className="rounded-lg bg-glass px-3 py-1.5 text-xs font-semibold text-fg-2 disabled:opacity-50"
        >
          {t.approval.cancel}
        </button>
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

export function StatusPill({ g }: { g: Generation }) {
  const STAGE = useI18n().t.generation.stage;
  const tone =
    g.status === "completed"
      ? "bg-success/15 text-success"
      : g.terminal
        ? "bg-danger/15 text-danger"
        : "bg-lime/15 text-lime";
  return <span className={clsx("rounded-md px-2 py-0.5 text-xs font-semibold", tone)}>{STAGE[g.status] ?? g.stage}</span>;
}

export function IconButton({
  children,
  label,
  onClick,
  href,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
}) {
  const cls = ICON_BUTTON;
  return href ? (
    <a href={href} download title={label} aria-label={label} className={cls} target="_blank" rel="noreferrer">
      {children}
    </a>
  ) : (
    <button type="button" title={label} aria-label={label} onClick={onClick} disabled={disabled} className={cls}>
      {children}
    </button>
  );
}
