"use client";

import clsx from "clsx";
import { AlertTriangle, ArrowDown, ArrowUp, Check, Factory, Loader2, Pause, PenLine, Play, Plus, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Chip, SettingCard } from "@/components/studio/controls";
import { CostPanel, costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import {
  costShort,
  FACTORY_MODEL,
  formatUsd,
  studio,
  type Estimate,
  type FactoryAspect,
  type FactoryInfo,
  type FactoryRich,
  type FactorySource,
  type FactoryItem,
  type FactoryLayout,
  type FactoryScene,
  type FactoryScript,
} from "@/lib/studio";
import type { FreeVoice, Voice } from "@/lib/types";

const LANGUAGES = ["es", "en", "pt", "fr", "it", "de"];
const DURATIONS = [20, 30, 45, 60, 75, 90, 120, 150, 180, 240, 300];
const RATES = ["-10%", "+0%", "+10%", "+20%"];
const ELEVEN_MODELS = ["eleven_v4", "eleven_v4_turbo", "eleven_flash_v2_5"];
const LAYOUTS: FactoryLayout[] = [
  "title",
  "counter",
  "timer",
  "map",
  "chart",
  "comparison",
  "list",
  "quote",
  "scale",
  "timeline",
  "equation",
  "plot",
  "signal",
  "spectrum",
  "diagram",
  "code",
  "surface3d",
  "objects3d",
  "globe3d",
  "bars3d",
  "particles3d",
  "sources",
  "closing",
];
/** Qué campos usa cada plantilla (el resto se oculta en el editor). */
const NUMBER_LAYOUTS = new Set<FactoryLayout>(["counter", "timer"]);
const UNIT_LAYOUTS = new Set<FactoryLayout>(["counter", "timer", "chart", "comparison", "scale", "bars3d"]);
const ITEM_LAYOUTS = new Set<FactoryLayout>(["map", "chart", "comparison", "list", "scale", "timeline", "objects3d", "globe3d", "bars3d"]);
const VALUE_ITEMS = new Set<FactoryLayout>(["chart", "comparison", "scale", "bars3d"]);
const GEO_ITEMS = new Set<FactoryLayout>(["map", "globe3d"]);
/** Campos técnicos de cada plantilla: se editan como JSON (la API los valida al cotizar). */
const RICH_FIELDS: Partial<Record<FactoryLayout, (keyof FactoryRich)[]>> = {
  equation: ["steps"],
  plot: ["curves", "x_range", "y_range", "t_range", "x_label", "y_label"],
  signal: ["waves"],
  spectrum: ["waves"],
  surface3d: ["expr"],
  particles3d: ["expr"],
  diagram: ["nodes", "edges"],
  code: ["language", "code", "highlight"],
};
const RICH_KEYS: (keyof FactoryRich)[] = ["steps", "curves", "x_range", "y_range", "t_range", "x_label", "y_label", "waves", "expr", "nodes", "edges", "code", "language", "highlight"];
const NOTE_ITEMS = new Set<FactoryLayout>(["list", "timeline"]);
const LIMITS = { headline: 110, kicker: 60, unit: 30, prefix: 8, label: 60, note: 80, narration: 700, items: 6, scenes: 20 };

type Engine = "edge" | "elevenlabs";

function num(text: string): number | undefined {
  const n = Number(text.replace(",", "."));
  return text.trim() === "" || !Number.isFinite(n) ? undefined : n;
}

/** Quita los campos vacíos antes de enviar: la API valida el guion de forma estricta. */
function cleanScript(s: FactoryScript): FactoryScript {
  const opt = (v?: string) => (v && v.trim() ? v.trim() : undefined);
  return {
    title: s.title.trim() || "Short",
    ...(opt(s.hook) ? { hook: opt(s.hook) } : {}),
    ...(opt(s.cliffhanger) ? { cliffhanger: opt(s.cliffhanger) } : {}),
    ...(s.episode ? { episode: s.episode } : {}),
    ...(s.episodes ? { episodes: s.episodes } : {}),
    ...(opt(s.series_title) ? { series_title: opt(s.series_title) } : {}),
    ...(s.sources?.length ? { sources: s.sources } : {}),
    scenes: s.scenes.map((sc) => {
      const v = sc.visual;
      // Solo los campos técnicos de la plantilla elegida, y sin vacíos.
      const rich: FactoryRich = {};
      for (const k of RICH_FIELDS[v.layout] ?? []) {
        const val = v[k];
        if (val === undefined || val === null || val === "" || (Array.isArray(val) && !val.length)) continue;
        (rich as Record<string, unknown>)[k] = val;
      }
      return {
        narration: sc.narration.trim(),
        visual: {
          layout: v.layout,
          headline: v.headline.trim(),
          ...(opt(v.kicker) ? { kicker: opt(v.kicker) } : {}),
          ...(opt(v.unit) ? { unit: opt(v.unit) } : {}),
          ...(opt(v.prefix) ? { prefix: opt(v.prefix) } : {}),
          ...(v.value !== undefined ? { value: v.value } : {}),
          ...(v.from_value !== undefined ? { from_value: v.from_value } : {}),
          ...rich,
          items: v.items
            .filter((it) => it.label.trim())
            .map((it) => ({
              label: it.label.trim(),
              ...(it.value !== undefined ? { value: it.value } : {}),
              ...(opt(it.note) ? { note: opt(it.note) } : {}),
              ...(it.lat !== undefined ? { lat: it.lat } : {}),
              ...(it.lon !== undefined ? { lon: it.lon } : {}),
            })),
        },
      };
    }),
  };
}

/** Suma las cotizaciones de cada episodio en una sola para el panel de costo. */
function combine(list: (Estimate | null)[]): Estimate | null {
  if (!list.length || list.some((e) => !e)) return null;
  const all = list as Estimate[];
  const order = ["exact", "approx", "formula", "unavailable"] as const;
  const kind = all.reduce<Estimate["kind"]>((k, e) => (order.indexOf(e.kind) > order.indexOf(k) ? e.kind : k), "exact");
  const priced = all.every((e) => e.usd !== null);
  return {
    ...all[0],
    kind,
    usd: priced ? all.reduce((a, e) => a + (e.usd ?? 0), 0) : null,
    credits: null,
    missing: [...new Set(all.flatMap((e) => e.missing))],
    reserve_usd: null,
    basis: all.length > 1 ? `${all.length} × ${all[0].basis}` : all[0].basis,
  };
}

export function ContentFactory() {
  const { t, locale } = useI18n();
  const f = t.factory;
  const [info, setInfo] = useState<FactoryInfo | null>(null);
  const [infoError, setInfoError] = useState<string | null>(null);
  const [style, setStyle] = useState("neon-grid");
  const [format, setFormat] = useState("what-if");
  const [customFormat, setCustomFormat] = useState("");
  const [aspect, setAspect] = useState<FactoryAspect>("9:16");
  const [research, setResearch] = useState(false);
  const [sources, setSources] = useState<FactorySource[]>([]);
  const [searches, setSearches] = useState(0);
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState(60);
  const [episodes, setEpisodes] = useState(1);
  const [language, setLanguage] = useState("es");
  const [engine, setEngine] = useState<Engine>("edge");
  const [freeVoices, setFreeVoices] = useState<FreeVoice[] | null>(null);
  const [elevenVoices, setElevenVoices] = useState<Voice[] | null>(null);
  const [voiceId, setVoiceId] = useState("");
  const [rate, setRate] = useState("+0%");
  const [elevenModel, setElevenModel] = useState("eleven_v4");
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  const [scripts, setScripts] = useState<FactoryScript[]>([]);
  const [active, setActive] = useState(0);
  const [writing, setWriting] = useState(false);
  const [scriptCost, setScriptCost] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [estimates, setEstimates] = useState<{ key: string; list: (Estimate | null)[]; error?: string } | null>(null);
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const keys = useRef<Record<string, string>>({});
  const { items, add, remove } = useGenerations();

  useEffect(() => {
    studio
      .factory(locale)
      .then((i) => {
        setInfo(i);
        setStyle((s) => (i.styles.some((x) => x.id === s) ? s : (i.styles[0]?.id ?? s)));
        setFormat((f) => (i.formats.some((x) => x.id === f) ? f : (i.formats[0]?.id ?? f)));
      })
      .catch((e) => setInfoError(e instanceof Error ? e.message : String(e)));
  }, [locale]);

  useEffect(() => {
    let alive = true;
    studio
      .freeVoices(language)
      .then((r) => {
        if (!alive) return;
        setFreeVoices(r.voices);
        if (engine === "edge") setVoiceId((v) => (r.voices.some((x) => x.voice_id === v) ? v : (r.voices[0]?.voice_id ?? "")));
      })
      .catch(() => alive && setFreeVoices([]));
    return () => {
      alive = false;
    };
  }, [language, engine]);

  useEffect(() => {
    if (engine !== "elevenlabs" || elevenVoices) return;
    studio
      .voices("", false)
      .then((r) => {
        setElevenVoices(r.voices);
        setVoiceId((v) => (r.voices.some((x) => x.voice_id === v) ? v : (r.voices[0]?.voice_id ?? "")));
      })
      .catch(() => setElevenVoices([]));
  }, [engine, elevenVoices]);

  useEffect(() => () => audio.current?.pause(), []);

  function play(key: string, url: string | null) {
    audio.current?.pause();
    if (playing === key || !url) {
      setPlaying(null);
      return;
    }
    const el = new Audio(url);
    audio.current = el;
    el.onended = () => setPlaying((k) => (k === key ? null : k));
    setPlaying(key);
    void el.play().catch(() => setPlaying(null));
  }

  function pickEngine(e: Engine) {
    setEngine(e);
    setVoiceId(e === "edge" ? (freeVoices?.[0]?.voice_id ?? "") : (elevenVoices?.[0]?.voice_id ?? ""));
  }

  const voice = useMemo(
    () =>
      engine === "edge"
        ? { engine, voice_id: voiceId, ...(rate !== "+0%" ? { rate } : {}) }
        : { engine, voice_id: voiceId, model_id: elevenModel },
    [engine, voiceId, rate, elevenModel],
  );

  const fmt = info?.formats.find((x) => x.id === format) ?? null;
  const durations = fmt ? DURATIONS.filter((d) => d >= fmt.min_seconds && d <= fmt.max_seconds) : DURATIONS.slice(1, 6);

  function pickFormat(id: string) {
    const next = info?.formats.find((x) => x.id === id);
    setFormat(id);
    if (!next) return;
    setDuration(next.default_seconds);
    setAspect(next.aspect);
    setResearch(next.research);
    if (!next.episodes) setEpisodes(1);
    if (info?.styles.some((x) => x.id === next.style)) setStyle(next.style);
  }

  const inputs = useMemo(
    () => scripts.map((s) => ({ script: cleanScript(s), style, voice, aspect, format, language })),
    [scripts, style, voice, aspect, format, language],
  );
  const inputsKey = JSON.stringify(inputs);
  const ready = scripts.length > 0 && !!voiceId;

  useEffect(() => {
    if (!ready) return;
    const timer = setTimeout(() => {
      const list = JSON.parse(inputsKey) as Record<string, unknown>[];
      Promise.all(list.map((input) => studio.estimate(FACTORY_MODEL, input)))
        .then((r) => setEstimates({ key: inputsKey, list: r }))
        .catch((e) => setEstimates({ key: inputsKey, list: [], error: e instanceof Error ? e.message : String(e) }));
    }, 500);
    return () => clearTimeout(timer);
  }, [inputsKey, ready]);

  const current = estimates?.key === inputsKey ? estimates : null;
  const total = current ? combine(current.list) : null;
  const confirming = confirmKey === inputsKey;

  // Tope del guion: se cotiza (sin llamar a Claude) cada vez que cambia la petición y es lo que se aprueba al pulsar.
  const scriptAsk = useMemo(
    () => ({
      topic: topic.trim(),
      style,
      format,
      ...(format === "custom" ? { custom_format: customFormat.trim() } : {}),
      aspect,
      research,
      duration_seconds: duration,
      episodes,
      language,
    }),
    [topic, style, format, customFormat, aspect, research, duration, episodes, language],
  );
  const scriptAskKey = JSON.stringify(scriptAsk);
  const [scriptQuote, setScriptQuote] = useState<{ key: string; max: number } | null>(null);
  useEffect(() => {
    if (scriptAsk.topic.length < 3 || (scriptAsk.format === "custom" && !scriptAsk.custom_format)) return;
    const timer = setTimeout(() => {
      studio.factoryScriptEstimate(scriptAsk).then(
        (q) => setScriptQuote({ key: scriptAskKey, max: q.max_usd }),
        () => setScriptQuote(null),
      );
    }, 400);
    return () => clearTimeout(timer);
  }, [scriptAsk, scriptAskKey]);
  const scriptMax = scriptQuote?.key === scriptAskKey ? scriptQuote.max : null;
  const scriptKey = useRef<{ ask: string; key: string } | null>(null);

  async function write() {
    if (!topic.trim()) {
      setError(f.topicRequired);
      return;
    }
    if (format === "custom" && !customFormat.trim()) {
      setError(f.customRequired);
      return;
    }
    if (scriptMax === null) return;
    setWriting(true);
    setError(null);
    // La misma petición reintentada lleva la misma clave: si la primera llegó, no se vuelve a cobrar.
    if (scriptKey.current?.ask !== scriptAskKey) scriptKey.current = { ask: scriptAskKey, key: crypto.randomUUID() };
    try {
      const key = scriptKey.current.key;
      // Tras este intento (bien o mal) la clave no se reutiliza: volver a pulsar es una nueva aprobación.
      scriptKey.current = null;
      const r = await studio.factoryScripts({ ...scriptAsk, max_usd: scriptMax }, key);
      setScripts(r.episodes.map((s) => ({ ...s, scenes: s.scenes.map((sc) => ({ ...sc, visual: { ...sc.visual, items: sc.visual.items ?? [] } })) })));
      setScriptCost(r.cost_usd);
      setSources(r.sources ?? []);
      setSearches(r.searches ?? 0);
      if (r.aspect) setAspect(r.aspect);
      setActive(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWriting(false);
    }
  }

  function blank() {
    const n = Math.max(1, episodes);
    setScripts(
      Array.from({ length: n }, (_, i) => ({
        title: topic.trim() || f.blankTitle,
        ...(n > 1 ? { episode: i + 1, episodes: n } : {}),
        scenes: [
          { narration: f.blankNarration, visual: { layout: "title" as FactoryLayout, headline: topic.trim().slice(0, 110) || f.blankHeadline, items: [] } },
          { narration: "", visual: { layout: "closing" as FactoryLayout, headline: "", items: [] } },
        ],
      })),
    );
    setScriptCost(null);
    setActive(0);
  }

  function updateScript(i: number, fn: (s: FactoryScript) => FactoryScript) {
    setScripts((prev) => prev.map((s, k) => (k === i ? fn(s) : s)));
  }

  async function generate() {
    if (!ready || submitting) return;
    if (!voiceId) {
      setError(f.voiceRequired);
      return;
    }
    if (!costAllowsDirectSubmit(total) && !confirming) {
      setConfirmKey(inputsKey);
      return;
    }
    setConfirmKey(null);
    setSubmitting(true);
    setError(null);
    try {
      for (const [i, input] of inputs.entries()) {
        const est = current?.list[i] ?? null;
        // Una clave por episodio y por contenido: reintentar el mismo pedido no lo duplica.
        const k = `${inputsKey}|${i}`;
        keys.current[k] ??= crypto.randomUUID();
        add(
          await studio.generate(
            FACTORY_MODEL,
            input,
            keys.current[k],
            false,
            est?.usd ?? null,
            {},
            est?.reserve_usd ?? null,
            !costAllowsDirectSubmit(est),
          ),
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  const history = items.filter((g) => g.model === FACTORY_MODEL);
  const script = scripts[active];
  const renderer = info?.renderer;
  const short = costShort(total);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[560px]">
        <div className="flex items-center gap-3 px-6 pt-5 pb-2">
          <span className="flex size-9 items-center justify-center rounded-xl bg-lime text-ink">
            <Factory className="size-5" />
          </span>
          <div className="min-w-0">
            <h1 className="headline text-[26px] leading-none">{f.title}</h1>
          </div>
          {scripts.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setScripts([]);
                setScriptCost(null);
                setSources([]);
                setSearches(0);
              }}
              className="ml-auto flex items-center gap-1.5 text-xs text-fg-3 hover:text-fg"
            >
              <RotateCcw className="size-3.5" /> {f.startOver}
            </button>
          )}
        </div>
        <p className="px-6 pb-3 text-sm text-fg-3">{f.subtitle}</p>

        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 pb-3">
          {infoError && <p className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">{infoError}</p>}
          {renderer && !renderer.available && (
            <p className="flex gap-2 rounded-2xl border border-warning/40 bg-warning/5 p-3 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {f.rendererUnavailable(renderer.reason ?? "")}
            </p>
          )}

          <p className="px-1 pt-1 text-[13px] font-semibold text-fg-2">{f.stepIdea}</p>
          <SettingCard label={f.format}>
            <div className="grid grid-cols-2 gap-2">
              {(info?.formats ?? []).map((x) => (
                <button
                  key={x.id}
                  type="button"
                  onClick={() => pickFormat(x.id)}
                  title={x.description}
                  className={clsx(
                    "rounded-xl border px-3 py-2 text-left transition-colors",
                    format === x.id ? "border-lime bg-lime/5" : "border-line hover:border-line-2",
                  )}
                >
                  <p className="truncate text-[13px] font-semibold">{x.name}</p>
                  <p className="mt-0.5 truncate text-[11px] text-fg-3">
                    {f.formatInfo(x.min_seconds, x.max_seconds)} · {x.aspects.join(" / ")}
                    {x.episodes ? ` · ${f.seriesOk}` : ""}
                  </p>
                </button>
              ))}
            </div>
            {fmt && <p className="mt-2 text-xs text-fg-3">{fmt.description}</p>}
            {format === "custom" && (
              <textarea
                value={customFormat}
                onChange={(e) => setCustomFormat(e.target.value.slice(0, 6000))}
                rows={5}
                placeholder={f.customFormatPlaceholder}
                aria-label={f.customFormat}
                className={clsx(inputCls, "mt-2 resize-y leading-relaxed")}
              />
            )}
          </SettingCard>
          <SettingCard label={f.style}>
            <div className="grid grid-cols-3 gap-2">
              {(info?.styles ?? []).map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setStyle(s.id)}
                  title={s.description}
                  className={clsx(
                    "group relative overflow-hidden rounded-xl border-2 text-left transition-colors",
                    style === s.id ? "border-lime" : "border-transparent hover:border-line-2",
                  )}
                >
                  <div className="relative aspect-[9/16] w-full" style={{ background: s.colors[0] }}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={s.preview} alt="" className="absolute inset-0 size-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
                    {style === s.id && (
                      <span className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-full bg-lime text-ink">
                        <Check className="size-3.5" />
                      </span>
                    )}
                  </div>
                  <div className="bg-surface-2 px-2 py-1.5">
                    <p className="truncate text-xs font-semibold">{s.name}</p>
                    <div className="mt-1 flex gap-1">
                      {s.colors.map((c) => (
                        <span key={c} className="size-2.5 rounded-full border border-white/20" style={{ background: c }} />
                      ))}
                    </div>
                  </div>
                </button>
              ))}
            </div>
            {info && <p className="mt-2 text-xs text-fg-3">{info.styles.find((s) => s.id === style)?.description}</p>}
          </SettingCard>

          <SettingCard label={f.topic}>
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value.slice(0, 500))}
              rows={2}
              placeholder={f.topicPlaceholder}
              className="w-full resize-none bg-transparent text-[16px] leading-relaxed outline-none placeholder:text-fg-4"
            />
          </SettingCard>

          <div className="grid grid-cols-2 gap-3">
            <SettingCard label={f.duration}>
              <div className="flex flex-wrap gap-1.5">
                {durations.map((d) => (
                  <Chip key={d} active={duration === d} onClick={() => setDuration(d)}>
                    {f.seconds(d)}
                  </Chip>
                ))}
              </div>
            </SettingCard>
            <SettingCard label={f.episodes}>
              <div className="flex flex-wrap gap-1.5">
                {Array.from({ length: fmt && !fmt.episodes ? 1 : (info?.max_episodes ?? 5) }, (_, i) => i + 1).map((n) => (
                  <Chip key={n} active={episodes === n} onClick={() => setEpisodes(n)}>
                    {n}
                  </Chip>
                ))}
              </div>
            </SettingCard>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <SettingCard label={f.aspect}>
              <div className="flex flex-wrap gap-1.5">
                {(fmt?.aspects ?? info?.aspects ?? ["9:16"]).map((a) => (
                  <Chip key={a} active={aspect === a} onClick={() => setAspect(a)}>
                    {f.aspects[a] ?? a}
                  </Chip>
                ))}
              </div>
            </SettingCard>
            <SettingCard label={f.research}>
              <label className="flex items-start gap-2 text-xs text-fg-3">
                <input type="checkbox" checked={research} onChange={(e) => setResearch(e.target.checked)} className="mt-0.5 accent-lime" />
                <span>{f.researchHint}</span>
              </label>
            </SettingCard>
          </div>

          <SettingCard label={f.language}>
            <div className="flex flex-wrap gap-1.5">
              {LANGUAGES.map((l) => (
                <Chip key={l} active={language === l} onClick={() => setLanguage(l)}>
                  {f.languages[l] ?? l}
                </Chip>
              ))}
            </div>
          </SettingCard>

          <SettingCard label={f.voice}>
            {info?.elevenlabs && (
              <div className="mb-2 flex gap-1.5">
                <Chip active={engine === "edge"} onClick={() => pickEngine("edge")}>
                  {f.freeVoices}
                </Chip>
                <Chip active={engine === "elevenlabs"} onClick={() => pickEngine("elevenlabs")}>
                  {f.elevenVoices}
                </Chip>
              </div>
            )}
            <VoiceList
              loading={engine === "edge" ? !freeVoices : !elevenVoices}
              voices={
                engine === "edge"
                  ? (freeVoices ?? []).map((v) => ({ id: v.voice_id, name: v.name, meta: `${v.country} · ${v.gender}`, url: studio.freeSampleUrl(v.voice_id, f.sample, rate) }))
                  : (elevenVoices ?? []).map((v) => ({ id: v.voice_id, name: v.name, meta: v.category ?? "", url: v.preview_url }))
              }
              selected={voiceId}
              onSelect={setVoiceId}
              playing={playing}
              onPlay={play}
              empty={f.noVoices}
              loadingText={f.loadingVoices}
              playLabel={f.play}
              stopLabel={f.stop}
            />
            {engine === "edge" ? (
              <div className="mt-2 flex items-center gap-1.5">
                <span className="mr-1 text-xs text-fg-3">{f.rate}</span>
                {RATES.map((r) => (
                  <Chip key={r} active={rate === r} onClick={() => setRate(r)}>
                    {r}
                  </Chip>
                ))}
              </div>
            ) : (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs text-fg-3">{f.elevenModel}</span>
                {ELEVEN_MODELS.map((m) => (
                  <Chip key={m} active={elevenModel === m} onClick={() => setElevenModel(m)}>
                    {m}
                  </Chip>
                ))}
              </div>
            )}
          </SettingCard>

          <p className="px-1 pt-1 text-[13px] font-semibold text-fg-2">{f.stepScript}</p>
          {info && !info.scripts.available && <p className="rounded-2xl bg-surface-2 p-3 text-sm text-fg-3">{f.scriptsUnavailable}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={write}
              disabled={writing || !info?.scripts.available || scriptMax === null}
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-2xl bg-surface-4 text-[15px] font-semibold hover:bg-white/10 disabled:opacity-50"
            >
              {writing ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4 text-lime" />}
              {writing ? f.writing : f.writeScript}
              {!writing && scriptMax !== null && <span className="text-[13px] font-normal text-fg-3">{f.upTo(formatUsd(scriptMax))}</span>}
            </button>
            <button
              type="button"
              onClick={blank}
              disabled={writing}
              className="flex h-12 items-center justify-center gap-2 rounded-2xl border border-line px-4 text-[14px] font-medium text-fg-2 hover:text-fg disabled:opacity-50"
            >
              <PenLine className="size-4" /> {f.blankScript}
            </button>
          </div>
          {scriptCost !== null && (
            <p className="px-1 text-xs text-fg-3">
              {f.scriptCost(formatUsd(scriptCost))}
              {searches > 0 ? ` · ${f.searches(searches)}` : ""}
            </p>
          )}
          {sources.length > 0 && (
            <SettingCard label={f.sources}>
              <ul className="space-y-1 text-xs">
                {sources.map((src) => (
                  <li key={src.url} className="truncate">
                    <a href={src.url} target="_blank" rel="noreferrer noopener" className="text-fg-2 underline decoration-line hover:text-lime">
                      {src.title}
                    </a>
                  </li>
                ))}
              </ul>
            </SettingCard>
          )}

          {script && (
            <>
              {scripts.length > 1 && (
                <div className="flex flex-wrap gap-1.5">
                  {scripts.map((s, i) => (
                    <Chip key={i} active={active === i} onClick={() => setActive(i)}>
                      {f.episode(i + 1)}
                    </Chip>
                  ))}
                </div>
              )}
              <ScriptEditor script={script} onChange={(fn) => updateScript(active, fn)} />
            </>
          )}
        </div>

        {scripts.length > 0 && (
          <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
            <p className="mb-1 px-1 text-[13px] font-semibold text-fg-2">{f.stepGenerate}</p>
            {error && <p className="mb-2 px-1 text-sm text-danger">{error}</p>}
            <CostPanel loading={ready && !current} estimate={total} error={current?.error ?? (voiceId ? undefined : f.voiceRequired)} needsConfirm={confirming} />
            <button
              type="button"
              onClick={generate}
              disabled={submitting || !ready || renderer?.available === false}
              className="flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] hover:brightness-105 active:translate-y-px disabled:opacity-50"
            >
              {submitting ? <Loader2 className="size-6 animate-spin" /> : confirming ? t.studio.generateAnyway : f.generateN(scripts.length)}
              {!submitting && !confirming && short && <span className="text-[19px]">{short}</span>}
            </button>
          </div>
        )}
        {scripts.length === 0 && error && <p className="px-6 pb-4 text-sm text-danger">{error}</p>}
      </aside>

      <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col rounded-panel border border-line bg-surface-1">
        <div className="flex items-center gap-2 px-5 pt-4 pb-3">
          <span className="flex h-10 items-center gap-2 rounded-xl bg-surface-4 px-3 text-[15px] font-medium">
            <Factory className="size-4" /> {f.results}
          </span>
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-5 pb-5">
          {history.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center py-20 text-center">
              <p className="headline text-[40px]">{f.title}</p>
              <p className="mt-3 max-w-md text-fg-3">{f.empty}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="grid" onDelete={remove} gallery={history} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function VoiceList({
  loading,
  voices,
  selected,
  onSelect,
  playing,
  onPlay,
  empty,
  loadingText,
  playLabel,
  stopLabel,
}: {
  loading: boolean;
  voices: { id: string; name: string; meta: string; url: string | null }[];
  selected: string;
  onSelect: (id: string) => void;
  playing: string | null;
  onPlay: (key: string, url: string | null) => void;
  empty: string;
  loadingText: string;
  playLabel: string;
  stopLabel: string;
}) {
  if (loading) return <p className="text-sm text-fg-3">{loadingText}</p>;
  if (!voices.length) return <p className="text-sm text-fg-3">{empty}</p>;
  return (
    <div className="thin-scrollbar max-h-56 space-y-1 overflow-y-auto pr-1">
      {voices.map((v) => (
        <div
          key={v.id}
          className={clsx(
            "flex items-center gap-2 rounded-xl border px-2 py-1.5",
            selected === v.id ? "border-lime/60 bg-lime/5" : "border-transparent hover:bg-white/5",
          )}
        >
          <button
            type="button"
            onClick={() => onPlay(v.id, v.url)}
            disabled={!v.url}
            aria-label={playing === v.id ? stopLabel : playLabel}
            title={playing === v.id ? stopLabel : playLabel}
            className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-4 text-fg-2 hover:text-lime disabled:opacity-40"
          >
            {playing === v.id ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
          <button type="button" onClick={() => onSelect(v.id)} className="min-w-0 flex-1 text-left">
            <p className="truncate text-sm font-medium">{v.name}</p>
            {v.meta && <p className="truncate text-xs text-fg-3">{v.meta}</p>}
          </button>
          {selected === v.id && <Check className="size-4 shrink-0 text-lime" />}
        </div>
      ))}
    </div>
  );
}

const inputCls = "w-full rounded-lg bg-surface-2 px-2.5 py-1.5 text-sm outline-none placeholder:text-fg-4 focus:ring-1 focus:ring-lime/50";

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={clsx("block min-w-0", className)}>
      <span className="mb-1 block text-[11px] text-fg-3">{label}</span>
      {children}
    </label>
  );
}

function TextInput({ value, onChange, max, placeholder }: { value?: string; onChange: (v: string) => void; max: number; placeholder?: string }) {
  return <input value={value ?? ""} maxLength={max} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className={inputCls} />;
}

/** Campo numérico que conserva lo que se escribe (p. ej. «3,» a medio teclear) y entrega el número. */
function NumberInput({ value, onChange }: { value?: number; onChange: (v: number | undefined) => void }) {
  const [text, setText] = useState(value === undefined ? "" : String(value));
  const [last, setLast] = useState(value);
  if (last !== value) {
    setLast(value);
    if (num(text) !== value) setText(value === undefined ? "" : String(value));
  }
  return (
    <input
      inputMode="decimal"
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const n = num(e.target.value);
        setLast(n);
        onChange(n);
      }}
      className={inputCls}
    />
  );
}

function ScriptEditor({ script, onChange }: { script: FactoryScript; onChange: (fn: (s: FactoryScript) => FactoryScript) => void }) {
  const { t } = useI18n();
  const f = t.factory;
  const words = script.scenes.reduce((a, s) => a + s.narration.split(/\s+/).filter(Boolean).length, 0);
  const chars = script.scenes.reduce((a, s) => a + s.narration.length, 0);

  function setScene(i: number, fn: (s: FactoryScene) => FactoryScene) {
    onChange((s) => ({ ...s, scenes: s.scenes.map((sc, k) => (k === i ? fn(sc) : sc)) }));
  }
  function move(i: number, d: number) {
    onChange((s) => {
      const scenes = [...s.scenes];
      const j = i + d;
      if (j < 0 || j >= scenes.length) return s;
      [scenes[i], scenes[j]] = [scenes[j], scenes[i]];
      return { ...s, scenes };
    });
  }

  return (
    <div className="space-y-3">
      <SettingCard label={script.episode ? `${f.series} · ${f.episode(script.episode)}` : f.titleField}>
        <TextInput value={script.title} max={120} onChange={(v) => onChange((s) => ({ ...s, title: v }))} />
        <div className="mt-2 grid grid-cols-1 gap-2">
          <Field label={f.hook}>
            <TextInput value={script.hook} max={300} onChange={(v) => onChange((s) => ({ ...s, hook: v }))} />
          </Field>
          {script.episodes && script.episodes > 1 && (
            <Field label={f.cliffhanger}>
              <TextInput value={script.cliffhanger} max={300} onChange={(v) => onChange((s) => ({ ...s, cliffhanger: v }))} />
            </Field>
          )}
        </div>
        <p className="mt-2 text-xs text-fg-3">{f.summary(script.scenes.length, chars, Math.round(words / 2.5 + script.scenes.length * 0.6 + 1))}</p>
      </SettingCard>

      {script.scenes.map((sc, i) => {
        const v = sc.visual;
        const layout = v.layout;
        return (
          <div key={i} className="rounded-2xl border border-line bg-surface-3 px-4 py-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="font-mono text-xs text-lime">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-[13px] font-semibold">{f.scene(i + 1)}</span>
              <select
                value={layout}
                onChange={(e) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, layout: e.target.value as FactoryLayout } }))}
                aria-label={f.layout}
                className="ml-auto rounded-lg bg-surface-2 px-2 py-1 text-xs outline-none"
              >
                {LAYOUTS.map((l) => (
                  <option key={l} value={l}>
                    {f.layouts[l] ?? l}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => move(i, -1)} disabled={i === 0} title={f.moveUp} aria-label={f.moveUp} className="text-fg-3 hover:text-fg disabled:opacity-30">
                <ArrowUp className="size-3.5" />
              </button>
              <button type="button" onClick={() => move(i, 1)} disabled={i === script.scenes.length - 1} title={f.moveDown} aria-label={f.moveDown} className="text-fg-3 hover:text-fg disabled:opacity-30">
                <ArrowDown className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onChange((s) => ({ ...s, scenes: s.scenes.filter((_, k) => k !== i) }))}
                disabled={script.scenes.length <= 1}
                title={f.removeScene}
                aria-label={f.removeScene}
                className="text-fg-3 hover:text-danger disabled:opacity-30"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
            <Field label={f.narration}>
              <textarea
                value={sc.narration}
                maxLength={LIMITS.narration}
                rows={3}
                onChange={(e) => setScene(i, (s) => ({ ...s, narration: e.target.value }))}
                className={clsx(inputCls, "resize-none leading-relaxed")}
              />
            </Field>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <Field label={f.headline} className="col-span-2">
                <TextInput value={v.headline} max={LIMITS.headline} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, headline: x } }))} />
              </Field>
              <Field label={f.kicker} className="col-span-2">
                <TextInput value={v.kicker} max={LIMITS.kicker} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, kicker: x } }))} />
              </Field>
              {NUMBER_LAYOUTS.has(layout) && (
                <>
                  <Field label={f.value}>
                    <NumberInput value={v.value} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, value: x } }))} />
                  </Field>
                  <Field label={f.fromValue}>
                    <NumberInput value={v.from_value} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, from_value: x } }))} />
                  </Field>
                  <Field label={f.prefix}>
                    <TextInput value={v.prefix} max={LIMITS.prefix} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, prefix: x } }))} />
                  </Field>
                </>
              )}
              {UNIT_LAYOUTS.has(layout) && (
                <Field label={f.unit}>
                  <TextInput value={v.unit} max={LIMITS.unit} onChange={(x) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, unit: x } }))} />
                </Field>
              )}
            </div>
            {ITEM_LAYOUTS.has(layout) && (
              <ItemsEditor layout={layout} items={v.items} onChange={(items) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, items } }))} />
            )}
            {RICH_FIELDS[layout] && (
              <RichEditor
                key={`${i}-${layout}`}
                fields={RICH_FIELDS[layout]!}
                visual={v}
                onChange={(patch) => setScene(i, (s) => ({ ...s, visual: { ...s.visual, ...patch } }))}
              />
            )}
          </div>
        );
      })}
      {script.scenes.length < LIMITS.scenes && (
        <button
          type="button"
          onClick={() => onChange((s) => ({ ...s, scenes: [...s.scenes, { narration: "", visual: { layout: "counter", headline: "", items: [] } }] }))}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-line text-sm text-fg-2 hover:text-fg"
        >
          <Plus className="size-4" /> {f.addScene}
        </button>
      )}
    </div>
  );
}

function ItemsEditor({ layout, items, onChange }: { layout: FactoryLayout; items: FactoryItem[]; onChange: (items: FactoryItem[]) => void }) {
  const { t } = useI18n();
  const f = t.factory;
  const set = (i: number, patch: Partial<FactoryItem>) => onChange(items.map((it, k) => (k === i ? { ...it, ...patch } : it)));
  const isMap = GEO_ITEMS.has(layout);
  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] text-fg-3">{f.items}</p>
      <div className="space-y-1.5">
        {items.map((it, i) => (
          <div key={i} className="flex items-end gap-1.5">
            <Field label={f.label} className="flex-[2]">
              <TextInput value={it.label} max={LIMITS.label} onChange={(x) => set(i, { label: x })} />
            </Field>
            {VALUE_ITEMS.has(layout) && (
              <Field label={f.value} className="flex-1">
                <NumberInput value={it.value} onChange={(x) => set(i, { value: x })} />
              </Field>
            )}
            {NOTE_ITEMS.has(layout) && (
              <Field label={f.note} className="flex-[2]">
                <TextInput value={it.note} max={LIMITS.note} onChange={(x) => set(i, { note: x })} />
              </Field>
            )}
            {isMap && (
              <>
                <Field label={f.lat} className="flex-1">
                  <NumberInput value={it.lat} onChange={(x) => set(i, { lat: x })} />
                </Field>
                <Field label={f.lon} className="flex-1">
                  <NumberInput value={it.lon} onChange={(x) => set(i, { lon: x })} />
                </Field>
              </>
            )}
            <button
              type="button"
              onClick={() => onChange(items.filter((_, k) => k !== i))}
              title={f.removeItem}
              aria-label={f.removeItem}
              className="mb-2 text-fg-3 hover:text-danger"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
      {items.length < LIMITS.items && (
        <button type="button" onClick={() => onChange([...items, { label: "" }])} className="mt-2 flex items-center gap-1.5 text-xs text-fg-2 hover:text-lime">
          <Plus className="size-3.5" /> {f.addItem}
        </button>
      )}
    </div>
  );
}

/** Campos técnicos de una escena como JSON: se aplica solo cuando el texto es JSON válido. */
function RichEditor({ fields, visual, onChange }: { fields: (keyof FactoryRich)[]; visual: FactoryRich; onChange: (patch: FactoryRich) => void }) {
  const { t } = useI18n();
  const f = t.factory;
  const pick = () => Object.fromEntries(fields.map((k) => [k, visual[k] ?? null]));
  const [text, setText] = useState(() => JSON.stringify(pick(), null, 2));
  const [bad, setBad] = useState(false);
  return (
    <div className="mt-3">
      <p className="mb-1 text-[11px] text-fg-3">{f.richFields}</p>
      <textarea
        value={text}
        spellCheck={false}
        rows={Math.min(14, Math.max(4, text.split("\n").length))}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value) as Record<string, unknown>;
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("object");
            const patch: Record<string, unknown> = {};
            for (const k of RICH_KEYS) if (fields.includes(k)) patch[k] = parsed[k] ?? undefined;
            setBad(false);
            onChange(patch as FactoryRich);
          } catch {
            setBad(true);
          }
        }}
        className={clsx(inputCls, "resize-y font-mono text-[12px] leading-snug", bad && "ring-1 ring-danger/60")}
      />
      <p className={clsx("mt-1 text-[11px]", bad ? "text-danger" : "text-fg-4")}>{bad ? f.richInvalid : f.richHint}</p>
    </div>
  );
}
