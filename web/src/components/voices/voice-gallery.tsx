"use client";

import clsx from "clsx";
import { Check, Copy, Loader2, Pause, Play, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Chip } from "@/components/studio/controls";
import { studio } from "@/lib/studio";
import type { FreeVoice, Voice, VoiceStatus } from "@/lib/types";

type Tab = "free" | "account" | "library";
const TABS: Tab[] = ["free", "account", "library"];
const SPEEDS = ["-10%", "+0%", "+10%", "+20%"];
const ACCENTS = ["colombian", "latin american", "mexican", "venezuelan", "caribbean", ""];
const MAX_TEXT = 300;

/** Una fila de voz: botón de escuchar, nombre, datos y acciones. */
type Card = { id: string; name: string; meta: string; badge: "free" | "paid"; note?: string | null };

/** Galería para escuchar voces en español: gratis (edge-tts, con tu texto) y de pago (ElevenLabs, su muestra). */
export function VoiceGallery() {
  const { t } = useI18n();
  const v = t.voices;
  const [tab, setTab] = useState<Tab>("free");
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
    const handle = setTimeout(() => {
      setLibrary(null);
      studio
        .libraryVoices({ language: "es", accent, gender: libGender === "all" ? "" : libGender, search: search.trim() })
        .then((r) => setLibrary(r.voices))
        .catch(() => setLibrary([]));
    }, 350);
    return () => clearTimeout(handle);
  }, [tab, status, accent, libGender, search]);

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

  // Cuenta: primero las voces en español, luego el resto.
  const accountCards = useMemo(() => {
    const cards = (account ?? []).map((x) => ({ voice: x, spanish: x.labels.language === "es" }));
    return [...cards.filter((c) => c.spanish), ...cards.filter((c) => !c.spanish)];
  }, [account]);

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
          <VoiceGrid
            items={account === null ? null : accountCards}
            empty={v.empty}
            render={({ voice: x, spanish }) => (
              <VoiceRow
                key={x.voice_id}
                card={{
                  id: x.voice_id,
                  name: x.name,
                  meta: [spanish ? null : v.otherLanguages, ...Object.values(x.labels)].filter(Boolean).join(" · "),
                  badge: "paid",
                  note: x.description,
                }}
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

      {tab === "library" && status?.configured && (
        <section className="mt-6 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-fg-3">{v.accent}</span>
            {ACCENTS.map((a) => (
              <Chip key={a || "all"} active={accent === a} onClick={() => setAccent(a)}>{v.accents[a]}</Chip>
            ))}
          </div>
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
  labels,
}: {
  card: Card;
  playing: boolean;
  loading: boolean;
  disabled: boolean;
  onPlay: () => void;
  labels: { play: string; stop: string; copyId: string; copied: string; free: string; paid: string };
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
    </li>
  );
}
