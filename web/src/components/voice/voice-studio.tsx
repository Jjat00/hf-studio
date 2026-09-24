"use client";

import clsx from "clsx";
import { AlertTriangle, Loader2, Pause, Play, Search, Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { CostPanel } from "@/components/studio/cost-panel";
import { Chip, SettingCard } from "@/components/studio/controls";
import { MediaSlot } from "@/components/studio/media-slot";
import { costShort, outputSrc, studio, StudioError, type Estimate } from "@/lib/studio";
import type { Generation, Voice, VoiceChangeBody, VoiceEffect, VoiceStatus } from "@/lib/types";

const EFFECTS: VoiceEffect[] = ["none", "deep", "monster", "ghost"];
type Source = { generationId?: string; url: string; label: string };

function sourceOf(g: Generation): Source | null {
  const out = g.outputs.find((o) => o.kind === "video");
  if (g.status !== "completed" || !out) return null;
  const prompt = typeof g.input.prompt === "string" ? g.input.prompt : g.model;
  return { generationId: g.id, url: outputSrc(out), label: prompt };
}

export function VoiceStudio() {
  const { t } = useI18n();
  const v = t.voice;
  const router = useRouter();
  const params = useSearchParams();
  const { items } = useGenerations();
  const video = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);

  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [duration, setDuration] = useState(0);
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState<number | null>(null);
  const [library, setLibrary] = useState(false);
  const [query, setQuery] = useState("");
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [voice, setVoice] = useState<Voice | null>(null);
  const [effect, setEffect] = useState<VoiceEffect>("none");
  const [originalVolume, setOriginalVolume] = useState(0);
  const [isolate, setIsolate] = useState(true);
  // Cotización junto a la petición que la produjo: solo vale si coincide con la actual.
  const [quoted, setQuoted] = useState<{ key: string; value: Estimate | null; error?: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const idempotency = useRef<string | null>(null);

  const videos = useMemo(() => items.map((g) => [g, sourceOf(g)] as const).filter(([, s]) => s), [items]);

  useEffect(() => {
    studio.voiceStatus().then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  // ?from=<id> (un video de la biblioteca) o ?reuse=<id> (un cambio de voz anterior).
  const from = params.get("from");
  const reuseId = params.get("reuse");
  useEffect(() => {
    if (reuseId) {
      studio
        .get(reuseId)
        .then((g) => {
          const i = g.input as Partial<VoiceChangeBody>;
          setStart(i.start ?? 0);
          setEnd(i.end ?? null);
          setEffect(i.effect ?? "none");
          setOriginalVolume(i.original_volume ?? 0);
          setIsolate(i.remove_background_noise ?? true);
          if (i.voice_id) {
            setVoice({ voice_id: i.voice_id, name: i.voice_name ?? i.voice_id, public_owner_id: i.public_owner_id ?? null,
                       preview_url: null, description: null, labels: {}, library: !!i.public_owner_id });  // prettier-ignore
          }
          if (i.source_url) setSource({ url: i.source_url, label: i.source_url });
          else if (i.source_generation_id) studio.get(i.source_generation_id).then((s) => setSource(sourceOf(s)));
        })
        .catch(() => undefined);
    } else if (from) {
      studio.get(from).then((g) => setSource(sourceOf(g))).catch(() => undefined);
    }
  }, [from, reuseId]);

  // Búsqueda de voces con un pequeño retardo.
  useEffect(() => {
    if (!status?.configured) return;
    let alive = true;
    const timer = setTimeout(() => {
      setVoices(null);
      studio
        .voices(query.trim(), library)
        .then((r) => alive && setVoices(r.voices))
        .catch(() => alive && setVoices([]));
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [query, library, status?.configured]);

  const body: VoiceChangeBody | null =
    source && voice
      ? {
          ...(source.generationId ? { source_generation_id: source.generationId } : { source_url: source.url }),
          start,
          ...(end !== null ? { end } : {}),
          voice_id: voice.voice_id,
          voice_name: voice.name,
          ...(voice.public_owner_id ? { public_owner_id: voice.public_owner_id } : {}),
          effect,
          original_volume: originalVolume,
          remove_background_noise: isolate,
        }
      : null;
  const bodyKey = body ? JSON.stringify(body) : "";

  // Costo siempre visible: se recalcula al cambiar el tramo o la fuente.
  useEffect(() => {
    if (!bodyKey || !status?.configured) return;
    let alive = true;
    const timer = setTimeout(() => {
      studio
        .voiceEstimate(JSON.parse(bodyKey))
        .then((value) => alive && setQuoted({ key: bodyKey, value }))
        .catch((e) => alive && setQuoted({ key: bodyKey, value: null, error: e instanceof Error ? e.message : String(e) }));
    }, 350);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [bodyKey, status?.configured]);
  const current = quoted?.key === bodyKey ? quoted : null;
  const estimate = current?.value ?? null;
  const estimating = !!bodyKey && !!status?.configured && !current;

  function playSegment() {
    const el = video.current;
    if (!el) return;
    el.currentTime = start;
    stopAt.current = end ?? el.duration;
    void el.play();
  }

  async function submit() {
    if (!body || !estimate) return;
    setSubmitting(true);
    setFormError(null);
    idempotency.current ??= crypto.randomUUID();
    try {
      const g = await studio.changeVoice(body, idempotency.current);
      idempotency.current = null;
      router.push(`/history/${g.id}`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
      if (e instanceof StudioError && e.status < 500) idempotency.current = null;
    } finally {
      setSubmitting(false);
    }
  }

  const segEnd = end ?? duration;
  const short = costShort(estimate);
  const credits = status?.credits_left;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
          <div className="px-1">
            <h1 className="headline text-[34px] text-lime">{v.title}</h1>
            <p className="mt-1 text-sm text-fg-3">{v.subtitle}</p>
          </div>
          {status && !status.configured && (
            <p className="flex items-start gap-2 rounded-2xl bg-warning/10 p-3 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {v.notConfigured}
            </p>
          )}

          <SettingCard label={v.source}>
            {source ? (
              <div className="flex items-center justify-between gap-3">
                <p className="line-clamp-2 min-w-0 text-sm">{source.label}</p>
                <button type="button" onClick={() => setSource(null)} className="shrink-0 text-sm text-lime hover:underline">
                  {v.change}
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="text-sm text-fg-2">{v.pick}</p>
                {videos.length === 0 ? (
                  <p className="text-xs text-fg-3">{v.noVideos}</p>
                ) : (
                  <div className="thin-scrollbar grid max-h-64 grid-cols-3 gap-2 overflow-y-auto">
                    {videos.map(([g, s]) => (
                      <button
                        key={g.id}
                        type="button"
                        onClick={() => {
                          setSource(s);
                          setStart(0);
                          setEnd(null);
                        }}
                        title={s!.label}
                        className="overflow-hidden rounded-xl bg-surface-3 ring-lime/70 hover:ring-2"
                      >
                        <video src={s!.url} muted playsInline preload="metadata" className="aspect-square w-full object-cover" />
                      </button>
                    ))}
                  </div>
                )}
                <p className="text-xs text-fg-3">{v.orUpload}</p>
                <MediaSlot
                  label={v.source}
                  hint=""
                  kind="video"
                  multiple={false}
                  max={1}
                  required={false}
                  value={undefined}
                  compact
                  onChange={(url) => typeof url === "string" && setSource({ url, label: url.split("/").pop() ?? url })}
                />
              </div>
            )}
          </SettingCard>

          <SettingCard label={v.segment}>
            <div className="grid grid-cols-2 gap-2">
              {([
                [v.start, start, (x: number) => setStart(x)],
                [v.end, segEnd, (x: number) => setEnd(x)],
              ] as const).map(([label, value, set]) => (
                <label key={label} className="flex flex-col gap-1 text-xs text-fg-3">
                  {label}
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    value={Number(value.toFixed(2))}
                    onChange={(e) => set(Math.max(0, Number(e.target.value)))}
                    className="rounded-lg bg-surface-4 px-2.5 py-2 text-sm font-semibold text-fg outline-none"
                  />
                  <button
                    type="button"
                    disabled={!source}
                    onClick={() => set(Number((video.current?.currentTime ?? 0).toFixed(2)))}
                    className="text-left text-[11px] text-lime hover:underline disabled:opacity-40"
                  >
                    {v.useCurrent}
                  </button>
                </label>
              ))}
            </div>
            <div className="mt-2 flex gap-1.5">
              <Chip active={false} onClick={playSegment}>
                <span className="flex items-center gap-1">
                  <Play className="size-3" /> {v.playSegment}
                </span>
              </Chip>
              <Chip
                active={start === 0 && end === null}
                onClick={() => {
                  setStart(0);
                  setEnd(null);
                }}
              >
                {v.whole}
              </Chip>
            </div>
          </SettingCard>

          <SettingCard label={v.voice}>
            <div className="mb-2 flex gap-1.5">
              <Chip active={!library} onClick={() => setLibrary(false)}>
                {v.mine}
              </Chip>
              <Chip active={library} onClick={() => setLibrary(true)}>
                {v.library}
              </Chip>
            </div>
            <div className="mb-2 flex items-center gap-2 rounded-lg bg-surface-4 px-2.5">
              <Search className="size-4 text-fg-3" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={v.search}
                className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-fg-4"
              />
            </div>
            <VoiceList voices={status && !status.configured ? [] : voices} selected={voice} onSelect={setVoice} empty={v.noVoices} />
          </SettingCard>

          <SettingCard label={v.effect}>
            <div className="flex flex-wrap gap-1.5">
              {EFFECTS.map((e) => (
                <Chip key={e} active={effect === e} onClick={() => setEffect(e)}>
                  {v.effects[e]}
                </Chip>
              ))}
            </div>
          </SettingCard>

          <SettingCard label={`${v.originalVolume}: ${Math.round(originalVolume * 100)}%`}>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(originalVolume * 100)}
              onChange={(e) => setOriginalVolume(Number(e.target.value) / 100)}
              className="w-full accent-lime"
            />
          </SettingCard>

          <SettingCard label={v.isolate}>
            <div className="flex gap-1.5">
              <Chip active={isolate} onClick={() => setIsolate(true)}>
                {t.controls.on}
              </Chip>
              <Chip active={!isolate} onClick={() => setIsolate(false)}>
                {t.controls.off}
              </Chip>
            </div>
            <p className="mt-2 text-xs text-fg-3">{v.isolateHint}</p>
          </SettingCard>
        </div>

        <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          {typeof credits === "number" && (
            <p className="mb-2 px-1 text-xs text-fg-3">{v.credits(credits.toLocaleString())}</p>
          )}
          {body ? (
            <CostPanel loading={estimating} estimate={estimate} error={current?.error} needsConfirm={false} />
          ) : (
            <p className="mb-2 px-1 text-sm text-fg-3">{source ? v.needVoice : v.pick}</p>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={!body || !estimate || submitting || !status?.configured}
            className="mt-2 flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] transition-[filter,transform] hover:brightness-105 active:translate-y-px disabled:opacity-50"
          >
            {submitting ? <Loader2 className="size-6 animate-spin" /> : v.open}
            {!submitting && short && (
              <span className="flex items-center gap-1 text-[19px]">
                <Sparkles className="size-4 fill-ink" /> {short}
              </span>
            )}
          </button>
        </div>
      </aside>

      <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col items-center justify-center gap-4 rounded-panel border border-line bg-surface-1 p-5">
        {source ? (
          <>
            <video
              ref={video}
              src={source.url}
              controls
              playsInline
              onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
              onTimeUpdate={(e) => {
                if (stopAt.current !== null && e.currentTarget.currentTime >= stopAt.current) {
                  e.currentTarget.pause();
                  stopAt.current = null;
                }
              }}
              className="max-h-[70vh] w-full rounded-2xl bg-surface-3 object-contain"
            />
            {duration > 0 && (
              <div className="relative h-2 w-full max-w-3xl rounded-full bg-surface-4">
                <div
                  className="absolute inset-y-0 rounded-full bg-lime"
                  style={{
                    left: `${(Math.min(start, duration) / duration) * 100}%`,
                    width: `${(Math.max(0, Math.min(segEnd, duration) - start) / duration) * 100}%`,
                  }}
                />
              </div>
            )}
            {duration > 0 && (
              <p className="font-mono text-xs text-fg-3">
                {start.toFixed(1)}s → {Math.min(segEnd, duration).toFixed(1)}s / {duration.toFixed(1)}s
              </p>
            )}
          </>
        ) : (
          <p className="text-fg-3">{v.pick}</p>
        )}
      </section>
    </div>
  );
}

function VoiceList({
  voices,
  selected,
  onSelect,
  empty,
}: {
  voices: Voice[] | null;
  selected: Voice | null;
  onSelect: (v: Voice) => void;
  empty: string;
}) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => () => audio.current?.pause(), []);

  function preview(v: Voice) {
    audio.current?.pause();
    if (playing === v.voice_id || !v.preview_url) {
      setPlaying(null);
      return;
    }
    audio.current = new Audio(v.preview_url);
    audio.current.onended = () => setPlaying(null);
    void audio.current.play();
    setPlaying(v.voice_id);
  }

  if (voices === null) return <div className="shimmer h-40 rounded-xl" />;
  if (voices.length === 0) return <p className="py-4 text-center text-sm text-fg-3">{empty}</p>;
  return (
    <ul className="thin-scrollbar flex max-h-72 flex-col gap-1 overflow-y-auto">
      {voices.map((v) => (
        <li key={v.voice_id}>
          <div
            className={clsx(
              "flex items-center gap-2 rounded-xl border-2 px-2 py-1.5",
              selected?.voice_id === v.voice_id ? "border-lime/70 bg-lime/10" : "border-transparent hover:bg-white/5",
            )}
          >
            <button
              type="button"
              disabled={!v.preview_url}
              onClick={() => preview(v)}
              aria-label={v.name}
              className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-glass text-fg-2 hover:text-fg disabled:opacity-30"
            >
              {playing === v.voice_id ? <Pause className="size-4" /> : <Play className="size-4" />}
            </button>
            <button type="button" onClick={() => onSelect(v)} className="min-w-0 flex-1 text-left">
              <p className="truncate text-sm font-semibold">{v.name}</p>
              <p className="truncate text-xs text-fg-3">
                {[...Object.values(v.labels), v.description].filter(Boolean).join(" · ")}
              </p>
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
