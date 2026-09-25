"use client";

import { AlertTriangle, Loader2, Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { AudioPlayer } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { CostPanel } from "@/components/studio/cost-panel";
import { Chip, SettingCard } from "@/components/studio/controls";
import { MediaSlot } from "@/components/studio/media-slot";
import { VoicePicker } from "@/components/voice/voice-studio";
import {
  AUDIO_SERVICES,
  costShort,
  outputSrc,
  studio,
  StudioError,
  type AudioService,
  type Estimate,
} from "@/lib/studio";
import type { Generation, Voice, VoiceStatus } from "@/lib/types";

const SERVICES = Object.keys(AUDIO_SERVICES) as AudioService[];
const TTS_MODELS = ["eleven_v3", "eleven_multilingual_v2", "eleven_flash_v2_5"] as const;
const TTS_MAX: Record<string, number> = { eleven_v3: 5000, eleven_multilingual_v2: 10000, eleven_flash_v2_5: 40000 };
const LANGUAGES = ["es", "en", "pt", "fr", "it", "de"];
type Source = { generationId?: string; url: string; label: string };

function sourceOf(g: Generation): Source | null {
  const out = g.outputs.find((o) => o.kind === "video" || o.kind === "audio");
  if (g.status !== "completed" || !out) return null;
  const label = typeof g.input.prompt === "string" ? g.input.prompt : typeof g.input.text === "string" ? g.input.text : g.model;
  return { generationId: g.id, url: outputSrc(out), label };
}

export function AudioStudio() {
  const { t } = useI18n();
  const a = t.audio;
  const router = useRouter();
  const params = useSearchParams();
  const { items } = useGenerations();

  const [service, setService] = useState<AudioService>(() => {
    const tab = params.get("tab");
    return (SERVICES as string[]).includes(tab ?? "") ? (tab as AudioService) : "text-to-speech";
  });
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  // Texto a voz
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<Voice | null>(null);
  const [ttsModel, setTtsModel] = useState<(typeof TTS_MODELS)[number]>("eleven_multilingual_v2");
  const [language, setLanguage] = useState<string | null>(null);
  // Efectos
  const [sfx, setSfx] = useState("");
  const [sfxSeconds, setSfxSeconds] = useState(5);
  const [loop, setLoop] = useState(false);
  const [influence, setInfluence] = useState(0.3);
  // Música
  const [music, setMusic] = useState("");
  const [musicSeconds, setMusicSeconds] = useState(30);
  const [instrumental, setInstrumental] = useState(true);
  // Aislar voz
  const [source, setSource] = useState<Source | null>(null);

  const [quoted, setQuoted] = useState<{ key: string; value: (Estimate & { audio_quote?: string }) | null; error?: string } | null>(null);
  const [quoteNonce, setQuoteNonce] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const idempotency = useRef<{ key: string; body: string } | null>(null);

  useEffect(() => {
    studio.voiceStatus().then(setStatus).catch(() => setStatus({ configured: false }));
  }, []);

  // ?reuse=<id>: rellena el formulario con una generación de audio anterior.
  const reuseId = params.get("reuse");
  useEffect(() => {
    if (!reuseId) return;
    studio
      .get(reuseId)
      .then((g) => {
        const svc = (Object.entries(AUDIO_SERVICES).find(([, m]) => m === g.model)?.[0] ?? "text-to-speech") as AudioService;
        const i = g.input as Record<string, never>;
        setService(svc);
        if (svc === "text-to-speech") {
          setText(i.text ?? "");
          setTtsModel(i.model_id ?? "eleven_multilingual_v2");
          setLanguage(i.language_code ?? null);
          if (i.voice_id) {
            setVoice({ voice_id: i.voice_id, name: i.voice_name ?? i.voice_id, public_owner_id: i.public_owner_id ?? null,
                       preview_url: null, description: null, labels: {}, library: !!i.public_owner_id });  // prettier-ignore
          }
        } else if (svc === "sound-effects") {
          setSfx(i.text ?? "");
          setSfxSeconds(i.duration_seconds ?? 5);
          setLoop(!!i.loop);
          setInfluence(i.prompt_influence ?? 0.3);
        } else if (svc === "music") {
          setMusic(i.prompt ?? "");
          setMusicSeconds(i.seconds ?? 30);
          setInstrumental(!!i.force_instrumental);
        } else if (i.source_url) {
          setSource({ url: i.source_url, label: i.source_url });
        } else if (i.source_generation_id) {
          studio.get(i.source_generation_id).then((s) => setSource(sourceOf(s)));
        }
      })
      .catch(() => undefined);
  }, [reuseId]);

  const body: Record<string, unknown> | null = useMemo(() => {
    if (service === "text-to-speech") {
      if (!text.trim() || !voice || text.length > TTS_MAX[ttsModel]) return null;
      return {
        text,
        voice_id: voice.voice_id,
        voice_name: voice.name,
        model_id: ttsModel,
        ...(voice.public_owner_id ? { public_owner_id: voice.public_owner_id } : {}),
        ...(language && ttsModel !== "eleven_multilingual_v2" ? { language_code: language } : {}),
      };
    }
    if (service === "sound-effects") {
      return sfx.trim() ? { text: sfx, duration_seconds: sfxSeconds, prompt_influence: influence, loop } : null;
    }
    if (service === "music") {
      return music.trim() ? { prompt: music, seconds: musicSeconds, force_instrumental: instrumental } : null;
    }
    if (!source) return null;
    return source.generationId ? { source_generation_id: source.generationId } : { source_url: source.url };
  }, [service, text, voice, ttsModel, language, sfx, sfxSeconds, influence, loop, music, musicSeconds, instrumental, source]);
  const bodyKey = body ? `${service}|${JSON.stringify(body)}` : "";

  // Costo siempre visible antes de generar.
  useEffect(() => {
    if (!bodyKey || !status?.configured) return;
    let alive = true;
    const [svc, json] = [bodyKey.slice(0, bodyKey.indexOf("|")) as AudioService, bodyKey.slice(bodyKey.indexOf("|") + 1)];
    const timer = setTimeout(() => {
      studio
        .audioEstimate(svc, JSON.parse(json))
        .then((value) => alive && setQuoted({ key: bodyKey, value }))
        .catch((e) => alive && setQuoted({ key: bodyKey, value: null, error: e instanceof Error ? e.message : String(e) }));
    }, 350);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [bodyKey, status?.configured, quoteNonce]);
  const current = quoted?.key === bodyKey ? quoted : null;
  const estimate = current?.value ?? null;
  const estimating = !!bodyKey && !!status?.configured && !current;

  async function submit() {
    const quote = current?.value?.audio_quote;
    if (!body || !quote) return;
    setSubmitting(true);
    setFormError(null);
    if (idempotency.current?.body !== bodyKey) idempotency.current = { key: crypto.randomUUID(), body: bodyKey };
    try {
      const g = await studio.createAudio(service, { ...body, audio_quote: quote }, idempotency.current.key);
      idempotency.current = null;
      router.push(`/history/${g.id}`);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
      if (e instanceof StudioError && e.status < 500) idempotency.current = null;
      if (e instanceof StudioError && e.status === 409) {
        setQuoted(null);
        setQuoteNonce((n) => n + 1);
      }
    } finally {
      setSubmitting(false);
    }
  }

  const sources = useMemo(() => items.map((g) => [g, sourceOf(g)] as const).filter(([, s]) => s), [items]);
  const recent = items.filter((g) => g.model === AUDIO_SERVICES[service] && g.status === "completed").slice(0, 8);
  const short = costShort(estimate);
  const credits = status?.credits_left;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <nav className="hide-scrollbar flex gap-5 overflow-x-auto px-6 pt-5">
          {SERVICES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setService(s)}
              className={`shrink-0 border-b-2 pb-2.5 text-[17px] font-medium tracking-[-0.01em] transition-colors ${
                service === s ? "border-fg text-fg" : "border-transparent text-fg-3 hover:text-fg-2"
              }`}
            >
              {a.tabs[s]}
            </button>
          ))}
        </nav>
        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
          {status && !status.configured && (
            <p className="flex items-start gap-2 rounded-2xl bg-warning/10 p-3 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {t.voice.notConfigured}
            </p>
          )}

          {service === "text-to-speech" && (
            <>
              <TextBox value={text} onChange={setText} label={a.text} hint={a.textHint}
                       counter={a.chars(text.length, TTS_MAX[ttsModel])} over={text.length > TTS_MAX[ttsModel]} />  {/* prettier-ignore */}
              <SettingCard label={t.voice.voice}>
                <VoicePicker enabled={!!status?.configured} selected={voice} onSelect={setVoice} />
              </SettingCard>
              <SettingCard label={a.model}>
                <div className="flex flex-wrap gap-1.5">
                  {TTS_MODELS.map((m) => (
                    <Chip key={m} active={ttsModel === m} onClick={() => setTtsModel(m)}>
                      {a.models[m]}
                    </Chip>
                  ))}
                </div>
              </SettingCard>
              {ttsModel !== "eleven_multilingual_v2" && (
                <SettingCard label={a.language}>
                  <div className="flex flex-wrap gap-1.5">
                    <Chip active={language === null} onClick={() => setLanguage(null)}>
                      {a.auto}
                    </Chip>
                    {LANGUAGES.map((l) => (
                      <Chip key={l} active={language === l} onClick={() => setLanguage(l)}>
                        {l.toUpperCase()}
                      </Chip>
                    ))}
                  </div>
                </SettingCard>
              )}
            </>
          )}

          {service === "sound-effects" && (
            <>
              <TextBox value={sfx} onChange={setSfx} label={a.sfx} hint={a.sfxHint} />
              <Slider label={`${a.duration}: ${sfxSeconds}s`} min={0.5} max={30} step={0.5} value={sfxSeconds} onChange={setSfxSeconds} />
              <Slider label={`${a.influence}: ${Math.round(influence * 100)}%`} min={0} max={1} step={0.05} value={influence} onChange={setInfluence} />
              <Toggle label={a.loop} value={loop} onChange={setLoop} on={t.controls.on} off={t.controls.off} />
            </>
          )}

          {service === "music" && (
            <>
              <TextBox value={music} onChange={setMusic} label={a.music} hint={a.musicHint} />
              <Slider label={`${a.duration}: ${musicSeconds}s`} min={3} max={300} step={1} value={musicSeconds} onChange={setMusicSeconds} />
              <Toggle label={a.instrumental} value={instrumental} onChange={setInstrumental} on={t.controls.on} off={t.controls.off} />
            </>
          )}

          {service === "voice-isolator" && (
            <SettingCard label={a.source}>
              {source ? (
                <div className="flex items-center justify-between gap-3">
                  <p className="line-clamp-2 min-w-0 text-sm">{source.label}</p>
                  <button type="button" onClick={() => setSource(null)} className="shrink-0 text-sm text-lime hover:underline">
                    {t.voice.change}
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-fg-2">{a.pickSource}</p>
                  <div className="thin-scrollbar flex max-h-64 flex-col gap-1 overflow-y-auto">
                    {sources.map(([g, s]) => (
                      <button key={g.id} type="button" onClick={() => setSource(s)}
                              className="truncate rounded-lg bg-surface-3 px-3 py-2 text-left text-sm hover:bg-white/5">
                        {s!.label}
                      </button>
                    ))}  {/* prettier-ignore */}
                  </div>
                  <p className="text-xs text-fg-3">{t.voice.orUpload}</p>
                  <div className="grid grid-cols-2 gap-2">
                    {(["video", "audio"] as const).map((kind) => (
                      <MediaSlot key={kind} label={kind === "video" ? t.history.filters.video : t.history.filters.audio} hint="" kind={kind}
                                 multiple={false} max={1} required={false} value={undefined} compact
                                 onChange={(url) => typeof url === "string" && setSource({ url, label: url.split("/").pop() ?? url })} />
                    ))}
                  </div>  {/* prettier-ignore */}
                </div>
              )}
            </SettingCard>
          )}
        </div>

        <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          {typeof credits === "number" && <p className="mb-2 px-1 text-xs text-fg-3">{t.voice.credits(credits.toLocaleString())}</p>}
          {body && <CostPanel loading={estimating} estimate={estimate} error={current?.error} needsConfirm={false} />}
          <button
            type="button"
            onClick={submit}
            disabled={!body || !current?.value?.audio_quote || submitting || !status?.configured}
            className="mt-2 flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] transition-[filter,transform] hover:brightness-105 active:translate-y-px disabled:opacity-50"
          >
            {submitting ? <Loader2 className="size-6 animate-spin" /> : a.generate}
            {!submitting && short && (
              <span className="flex items-center gap-1 text-[19px]">
                <Sparkles className="size-4 fill-ink" /> {short}
              </span>
            )}
          </button>
        </div>
      </aside>

      <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col gap-4 rounded-panel border border-line bg-surface-1 p-5">
        <div>
          <h1 className="headline text-[34px] text-lime">{a.title}</h1>
          <p className="mt-1 text-sm text-fg-3">{a.subtitle}</p>
        </div>
        <h2 className="text-sm font-semibold text-fg-2">{a.recent}</h2>
        {recent.length === 0 ? (
          <p className="text-sm text-fg-3">{a.noRecent}</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {recent.map((g) => (
              <button key={g.id} type="button" onClick={() => router.push(`/history/${g.id}`)} className="text-left">
                <AudioPlayer src={outputSrc(g.outputs[0])} />
                <p className="mt-2 line-clamp-2 px-1 text-sm text-fg-2">
                  {String(g.input.text ?? g.input.prompt ?? "")}
                </p>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TextBox({ value, onChange, label, hint, counter, over }: {
  value: string; onChange: (v: string) => void; label: string; hint: string; counter?: string; over?: boolean;
}) {  // prettier-ignore
  return (
    <div className="rounded-2xl border border-line bg-surface-3 p-4 focus-within:border-line-2">
      <p className="mb-2 text-[13px] text-fg-3">{label}</p>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={5}
        className="w-full resize-none bg-transparent text-[16px] leading-relaxed outline-none placeholder:text-fg-4"
      />
      <div className="mt-1 flex items-start justify-between gap-3 text-xs text-fg-3">
        <span>{hint}</span>
        {counter && <span className={`shrink-0 font-mono ${over ? "text-danger" : ""}`}>{counter}</span>}
      </div>
    </div>
  );
}

function Slider({ label, min, max, step, value, onChange }: {
  label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void;
}) {  // prettier-ignore
  return (
    <SettingCard label={label}>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-lime" />
    </SettingCard>
  );
}

function Toggle({ label, value, onChange, on, off }: {
  label: string; value: boolean; onChange: (v: boolean) => void; on: string; off: string;
}) {  // prettier-ignore
  return (
    <SettingCard label={label}>
      <div className="flex gap-1.5">
        <Chip active={value} onClick={() => onChange(true)}>{on}</Chip>
        <Chip active={!value} onClick={() => onChange(false)}>{off}</Chip>
      </div>
    </SettingCard>
  );
}
