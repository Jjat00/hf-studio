"use client";

import clsx from "clsx";
import { Check, Copy, Loader2, Pause, Play, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Chip } from "@/components/studio/controls";
import { VoiceCreate } from "@/components/voices/voice-create";
import { studio } from "@/lib/studio";
import type { FreeVoice, Voice, VoiceStatus } from "@/lib/types";

type Tab = "free" | "account" | "library" | "create";
const TABS: Tab[] = ["free", "account", "library", "create"];
/** Voces que la persona creó (clonadas o diseñadas): se pueden borrar para liberar su espacio. */
const OWN_CATEGORIES = new Set(["cloned", "generated"]);
const SPEEDS = ["-10%", "+0%", "+10%", "+20%"];
const ACCENTS = ["colombian", "latin american", "mexican", "venezuelan", "caribbean", ""];
const MAX_TEXT = 300;
/** Idiomas con voces gratis (edge-tts) y en la biblioteca de ElevenLabs (códigos ISO 639-1). */
const LANGUAGES = ["es", "en", "pt", "fr", "it", "de", "nl", "pl", "ru", "tr", "ar", "hi", "ja", "ko", "zh"];
/** Texto de prueba en el idioma de la voz (el de español viene del diccionario). */
const SAMPLES: Record<string, string> = {
  en: "Hi, here is today's artificial intelligence news. OpenAI just launched agents that work for you around the clock.",
  pt: "Olá, estas são as notícias de inteligência artificial de hoje. A OpenAI acaba de lançar agentes que trabalham para você o dia todo.",
  fr: "Bonjour, voici les actualités de l'intelligence artificielle du jour. OpenAI vient de lancer des agents qui travaillent pour vous jour et nuit.",
  it: "Ciao, ecco le notizie di intelligenza artificiale di oggi. OpenAI ha appena lanciato agenti che lavorano per te giorno e notte.",
  de: "Hallo, hier sind die heutigen Nachrichten zur künstlichen Intelligenz. OpenAI hat gerade Agenten vorgestellt, die rund um die Uhr für dich arbeiten.",
  nl: "Hallo, dit is het nieuws over kunstmatige intelligentie van vandaag. OpenAI heeft net agents gelanceerd die dag en nacht voor je werken.",
  pl: "Cześć, oto dzisiejsze wiadomości o sztucznej inteligencji. OpenAI właśnie uruchomiło agentów, którzy pracują dla ciebie całą dobę.",
  ru: "Привет, вот сегодняшние новости об искусственном интеллекте. OpenAI только что запустила агентов, которые работают на вас круглосуточно.",
  tr: "Merhaba, işte bugünün yapay zekâ haberleri. OpenAI, sizin için günün her saati çalışan ajanları az önce tanıttı.",
  ar: "مرحبًا، هذه أخبار الذكاء الاصطناعي لهذا اليوم. أطلقت OpenAI للتو وكلاء يعملون من أجلك على مدار الساعة.",
  hi: "नमस्ते, ये हैं आज की आर्टिफ़िशियल इंटेलिजेंस की खबरें। OpenAI ने अभी ऐसे एजेंट लॉन्च किए हैं जो आपके लिए चौबीसों घंटे काम करते हैं।",
  ja: "こんにちは、今日の人工知能のニュースです。OpenAIは、あなたのために24時間働くエージェントを発表しました。",
  ko: "안녕하세요, 오늘의 인공지능 뉴스입니다. OpenAI가 하루 종일 당신을 위해 일하는 에이전트를 막 출시했습니다.",
  zh: "你好，这是今天的人工智能新闻。OpenAI 刚刚推出了全天候为你工作的智能体。",
};

/** Una fila de voz: botón de escuchar, nombre, datos y acciones. */
type Card = { id: string; name: string; meta: string; badge: "free" | "paid"; note?: string | null };

/** Galería para escuchar voces por idioma: gratis (edge-tts, con tu texto) y de pago (ElevenLabs, su muestra). */
export function VoiceGallery() {
  const { t, locale } = useI18n();
  const v = t.voices;
  const [tab, setTab] = useState<Tab>("free");
  const [lang, setLang] = useState("es");
  const sampleFor = (l: string) => (l === "es" ? v.sampleDefault : (SAMPLES[l] ?? v.sampleDefault));
  const [text, setText] = useState(v.sampleDefault);
  const [rate, setRate] = useState("+0%");

  const [free, setFree] = useState<FreeVoice[] | null>(null);
  const [freeError, setFreeError] = useState<string | null>(null);
  const [country, setCountry] = useState("Colombia");
  const [gender, setGender] = useState("all");

  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [account, setAccount] = useState<Voice[] | null>(null);
  const [library, setLibrary] = useState<Voice[] | null>(null);
  const [accent, setAccent] = useState("colombian");
  const [libGender, setLibGender] = useState("all");
  const [search, setSearch] = useState("");

  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [playError, setPlayError] = useState<string | null>(null);

  useEffect(() => {
    studio.freeVoices().then((r) => setFree(r.voices)).catch((e) => setFreeError(String(e.message ?? e)));
    studio.voiceStatus().then(setStatus).catch(() => setStatus({ configured: false }));
    return () => audio.current?.pause();
  }, []);

  useEffect(() => {
    if (tab === "account" && status?.configured && account === null) {
      studio.voices("", false).then((r) => setAccount(r.voices)).catch(() => setAccount([]));
    }
  }, [tab, status, account]);

  useEffect(() => {
    if (tab !== "library" || !status?.configured) return;
    let current = true; // una respuesta vieja (otro idioma o filtro) no pisa la nueva
    const handle = setTimeout(() => {
      setLibrary(null);
      studio
        .libraryVoices({
          language: lang,
          accent: lang === "es" ? accent : "",
          gender: libGender === "all" ? "" : libGender,
          search: search.trim(),
        })
        .then((r) => current && setLibrary(r.voices))
        .catch(() => current && setLibrary([]));
    }, 350);
    return () => {
      current = false;
      clearTimeout(handle);
    };
  }, [tab, status, lang, accent, libGender, search]);

  function chooseLanguage(next: string) {
    if (next === lang) return;
    stop();
    // Cambia el texto de prueba solo si la persona no escribió el suyo.
    if (text.trim() === sampleFor(lang)) setText(sampleFor(next));
    setLang(next);
    setCountry(next === "es" ? "Colombia" : "");
    setFree(null);
    setFreeError(null);
    studio.freeVoices(next).then((r) => setFree(r.voices)).catch((e) => setFreeError(String(e.message ?? e)));
  }

  const languageName = useMemo(() => {
    let names: Intl.DisplayNames | null = null;
    try {
      names = new Intl.DisplayNames([locale], { type: "language" });
    } catch {
      /* navegador sin Intl.DisplayNames: se muestra el código */
    }
    return (code: string) => {
      const name = names?.of(code) ?? code;
      return name.charAt(0).toLocaleUpperCase(locale) + name.slice(1);
    };
  }, [locale]);

  async function removeVoice(x: Voice) {
    if (!window.confirm(v.deleteConfirm(x.name))) return;
    try {
      await studio.deleteVoice(x.voice_id);
      setAccount((all) => (all ?? []).filter((y) => y.voice_id !== x.voice_id));
    } catch (e) {
      setPlayError(e instanceof Error ? e.message : String(e));
    }
  }

  function stop() {
    audio.current?.pause();
    setPlaying(null);
  }

  function play(key: string, url: string | null) {
    audio.current?.pause();
    setPlayError(null);
    if (playing === key || !url) {
      setPlaying(null);
      return;
    }
    const el = new Audio(url);
    audio.current = el;
    setLoading(key);
    el.oncanplay = () => setLoading((k) => (k === key ? null : k));
    el.onended = () => setPlaying(null);
    el.onerror = () => {
      setLoading(null);
      setPlaying(null);
      setPlayError(v.sampleError);
    };
    void el.play().catch(() => undefined);
    setPlaying(key);
  }

  const cleanText = text.trim().slice(0, MAX_TEXT);
  const countries = useMemo(() => {
    const seen = new Set<string>();
    (free ?? []).forEach((x) => seen.add(x.country));
    return [...seen];
  }, [free]);

  const freeCards: (Card & { voice: FreeVoice })[] = (free ?? [])
    .filter((x) => (country === "" || x.country === country) && (gender === "all" || x.gender === gender))
    .map((x) => ({
      id: x.voice_id,
      name: x.name,
      meta: [x.country, v.genders[x.gender] ?? x.gender, ...x.personalities].filter(Boolean).join(" · "),
      badge: "free" as const,
      voice: x,
    }));

  // Cuenta: solo las voces del idioma elegido.
  const accountCards = useMemo(() => (account ?? []).filter((x) => x.labels.language === lang), [account, lang]);

  return (
    <div className="px-4 py-8 md:px-8">
      <div>
        <h1 className="headline text-[40px] md:text-[56px]">{v.title}</h1>
        <p className="mt-2 max-w-3xl text-fg-3">{v.subtitle}</p>
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {TABS.map((k) => (
          <Chip key={k} active={tab === k} onClick={() => { stop(); setTab(k); }}>{v.tabs[k]}</Chip>
        ))}
      </div>

      {tab !== "create" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-fg-3">{v.language}</span>
          {LANGUAGES.map((l) => (
            <Chip key={l} active={lang === l} onClick={() => chooseLanguage(l)}>{languageName(l)}</Chip>
          ))}
        </div>
      )}

      {tab === "free" && (
        <section className="mt-6 flex flex-col gap-4">
          <div className="rounded-2xl border border-line bg-surface-3 px-4 py-3">
            <label htmlFor="voice-sample-text" className="mb-2 block text-[13px] text-fg-3">
              {v.sampleLabel}
            </label>
            <textarea
              id="voice-sample-text"
              value={text}
              maxLength={MAX_TEXT}
              onChange={(e) => setText(e.target.value)}
              rows={2}
              className="w-full resize-none rounded-lg bg-transparent text-sm outline-none"
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-fg-3">{v.speed}</span>
              {SPEEDS.map((r) => (
                <Chip key={r} active={rate === r} onClick={() => setRate(r)}>{v.speeds[r]}</Chip>
              ))}
              <span className="ml-auto text-xs text-fg-3 tabular-nums">{text.length}/{MAX_TEXT}</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-fg-3">{v.country}</span>
            {countries.map((c) => (
              <Chip key={c} active={country === c} onClick={() => setCountry(c)}>{c}</Chip>
            ))}
            <Chip active={country === ""} onClick={() => setCountry("")}>{v.all}</Chip>
          </div>
          <GenderFilter value={gender} onChange={setGender} labels={v.genders} title={v.gender} />
          <p className="text-xs text-fg-3">{v.freeHint}</p>
          {freeError && <p className="text-sm text-danger">{freeError}</p>}
          <VoiceGrid
            items={free === null && !freeError ? null : freeCards}
            empty={v.empty}
            render={(c) => (
              <VoiceRow
                key={c.id}
                card={c}
                playing={playing === c.id}
                loading={loading === c.id}
                disabled={!cleanText}
                onPlay={() => play(c.id, studio.freeSampleUrl(c.id, cleanText, rate))}
                labels={v}
              />
            )}
          />
        </section>
      )}

      {tab !== "free" && status && !status.configured && (
        <p className="mt-6 rounded-2xl border border-line bg-surface-3 px-4 py-3 text-sm text-fg-3">{v.notConfigured}</p>
      )}

      {tab === "account" && status?.configured && (
        <section className="mt-6 flex flex-col gap-4">
          <p className="max-w-3xl text-xs text-fg-3">{v.accountHint}</p>
          {account !== null && accountCards.length === 0 ? (
            <p className="py-6 text-center text-sm text-fg-3">
              {v.noAccountVoices(languageName(lang))}{" "}
              <button type="button" onClick={() => setTab("library")} className="font-medium text-lime hover:underline">
                {v.searchLibrary}
              </button>
            </p>
          ) : (
          <VoiceGrid
            items={account === null ? null : accountCards}
            empty={v.empty}
            render={(x) => (
              <VoiceRow
                key={x.voice_id}
                card={{
                  id: x.voice_id,
                  name: x.name,
                  meta: Object.values(x.labels).filter(Boolean).join(" · "),
                  badge: "paid",
                  note: x.description,
                }}
                playing={playing === x.voice_id}
                loading={loading === x.voice_id}
                disabled={!x.preview_url}
                onPlay={() => play(x.voice_id, x.preview_url)}
                onDelete={OWN_CATEGORIES.has(x.category ?? "") ? () => void removeVoice(x) : undefined}
                labels={v}
              />
            )}
          />
          )}
        </section>
      )}

      {tab === "create" && status?.configured && <VoiceCreate canClone={status.can_clone} onCreated={() => setAccount(null)} />}

      {tab === "library" && status?.configured && (
        <section className="mt-6 flex flex-col gap-4">
          {lang === "es" && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-fg-3">{v.accent}</span>
              {ACCENTS.map((a) => (
                <Chip key={a || "all"} active={accent === a} onClick={() => setAccent(a)}>{v.accents[a]}</Chip>
              ))}
            </div>
          )}
          <GenderFilter value={libGender} onChange={setLibGender} labels={v.genders} title={v.gender} />
          <label className="flex h-9 max-w-sm items-center gap-2 rounded-lg bg-glass px-3">
            <Search className="size-4 text-fg-3" />
            <input
              id="voice-library-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={v.search}
              aria-label={v.search}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </label>
          <p className="max-w-3xl text-xs text-fg-3">{v.libraryHint}</p>
          <VoiceGrid
            items={library}
            empty={v.empty}
            render={(x) => (
              <VoiceRow
                key={x.voice_id}
                card={{ id: x.voice_id, name: x.name, meta: Object.values(x.labels).join(" · "), badge: "paid", note: x.description }}
                playing={playing === x.voice_id}
                loading={loading === x.voice_id}
                disabled={!x.preview_url}
                onPlay={() => play(x.voice_id, x.preview_url)}
                labels={v}
              />
            )}
          />
        </section>
      )}

      {playError && <p className="mt-4 text-sm text-danger">{playError}</p>}
    </div>
  );
}

function GenderFilter({ value, onChange, labels, title }: { value: string; onChange: (v: string) => void; labels: Record<string, string>; title: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-fg-3">{title}</span>
      {["all", "female", "male"].map((g) => (
        <Chip key={g} active={value === g} onClick={() => onChange(g)}>{labels[g]}</Chip>
      ))}
    </div>
  );
}

function VoiceGrid<T>({ items, empty, render }: { items: T[] | null; empty: string; render: (item: T) => React.ReactNode }) {
  if (items === null) return <div className="shimmer h-40 rounded-xl" />;
  if (items.length === 0) return <p className="py-6 text-center text-sm text-fg-3">{empty}</p>;
  return <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">{items.map(render)}</ul>;
}

function VoiceRow({
  card,
  playing,
  loading,
  disabled,
  onPlay,
  onDelete,
  labels,
}: {
  card: Card;
  playing: boolean;
  loading: boolean;
  disabled: boolean;
  onPlay: () => void;
  onDelete?: () => void;
  labels: { play: string; stop: string; copyId: string; copied: string; free: string; paid: string; deleteVoice: string };
}) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(card.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* el portapapeles puede estar bloqueado; el ID sigue visible en el título */
    }
  }
  return (
    <li
      className={clsx(
        "flex items-start gap-3 rounded-2xl border bg-surface-3 px-3 py-3",
        playing ? "border-lime/60" : "border-line",
      )}
    >
      <button
        type="button"
        onClick={onPlay}
        disabled={disabled}
        aria-label={`${playing ? labels.stop : labels.play}: ${card.name}`}
        className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-glass text-fg-2 hover:text-fg disabled:opacity-30"
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-semibold" title={card.id}>
            {card.name}
          </p>
          <span
            className={clsx(
              "shrink-0 rounded-md px-1.5 py-0.5 text-[10px] leading-3 font-bold",
              card.badge === "free" ? "bg-lime/20 text-lime" : "bg-white/10 text-fg-2",
            )}
          >
            {card.badge === "free" ? labels.free : labels.paid}
          </span>
        </div>
        <p className="truncate text-xs text-fg-3">{card.meta}</p>
        {card.note && <p className="mt-1 line-clamp-2 text-xs text-fg-3">{card.note}</p>}
      </div>
      <button
        type="button"
        onClick={copy}
        title={card.id}
        aria-label={`${labels.copyId}: ${card.id}`}
        className="flex size-8 shrink-0 items-center justify-center rounded-lg text-fg-3 hover:text-fg"
      >
        {copied ? <Check className="size-4 text-lime" /> : <Copy className="size-4" />}
      </button>
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={`${labels.deleteVoice}: ${card.name}`}
          title={labels.deleteVoice}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-fg-3 hover:text-danger"
        >
          <Trash2 className="size-4" />
        </button>
      )}
    </li>
  );
}
