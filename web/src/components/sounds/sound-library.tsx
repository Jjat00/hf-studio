"use client";

import clsx from "clsx";
import {
  AudioLines,
  Check,
  Copy,
  Download,

  ExternalLink,
  Ghost,
  Laugh,
  Loader2,
  Mic,
  Music,
  Pause,
  Play,
  Search,
  Shapes,
  Trees,
  Wand2,
  X,
  Zap,
  Footprints,
  Volume2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio } from "@/lib/studio";
import type { Sound } from "@/lib/types";

const BASE = "/api/studio";
const ORDER = ["voice", "scream", "laugh", "creature", "ambience", "impact", "foley", "transition", "music", "other"];
const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  voice: Mic, scream: Volume2, laugh: Laugh, creature: Ghost, ambience: Trees, impact: Zap,
  foley: Footprints, transition: Wand2, music: Music, other: Shapes,
};  // prettier-ignore

function seconds(d: number | null) {
  if (d === null) return "";
  return d < 60 ? `${d.toFixed(1)}s` : `${Math.floor(d / 60)}:${String(Math.round(d % 60)).padStart(2, "0")}`;
}

export function SoundLibrary() {
  const { t, locale } = useI18n();
  const s = t.sounds;
  const [sounds, setSounds] = useState<Sound[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [category, setCategory] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await studio.sounds();
      setSounds(r.sounds);
      setCounts(r.counts);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSounds([]);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- carga inicial desde la API
    void load();
    return () => audio.current?.pause();
  }, [load]);

  function toggle(sound: Sound) {
    audio.current?.pause();
    if (playing === sound.id) {
      setPlaying(null);
      return;
    }
    audio.current = new Audio(BASE + sound.file_url);
    audio.current.onended = () => setPlaying(null);
    void audio.current.play();
    setPlaying(sound.id);
  }

  async function importHistory() {
    setImporting(true);
    setNotice(null);
    try {
      const r = await studio.importElevenlabs();
      setNotice(s.imported(r.imported));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }

  async function update(id: string, patch: { title?: string; category?: string; tags?: string[] }) {
    const updated = await studio.updateSound(id, patch);
    setSounds((list) => list?.map((x) => (x.id === id ? { ...x, ...updated, source: x.source } : x)) ?? null);
    if (patch.category) await load();
  }

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (sounds ?? []).filter(
      (x) =>
        (!category || x.category === category) &&
        (!needle || `${x.title} ${x.text} ${x.tags.join(" ")}`.toLowerCase().includes(needle)),
    );
  }, [sounds, category, query]);

  // Sin filtro ni búsqueda, agrupados por categoría; si no, una sola lista.
  const groups = category || query.trim() ? [[category ?? "", shown] as const] : ORDER.map((c) => [c, shown.filter((x) => x.category === c)] as const).filter(([, l]) => l.length);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div className="px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline text-[40px] md:text-[56px]">{s.title}</h1>
          <p className="mt-2 max-w-2xl text-fg-3">{s.subtitle}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={importHistory}
            disabled={importing}
            title={s.importHint}
            className="flex h-10 items-center gap-2 rounded-xl bg-glass px-4 text-sm font-semibold text-fg-2 hover:text-fg disabled:opacity-50"
          >
            {importing ? <Loader2 className="size-4 animate-spin" /> : <AudioLines className="size-4" />}
            {importing ? s.importing : s.import}
          </button>
          {notice && <p className="text-xs text-lime">{notice}</p>}
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 rounded-xl bg-surface-2 px-3 md:max-w-md">
        <Search className="size-4 text-fg-3" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={s.search}
          className="h-10 w-full bg-transparent text-sm outline-none placeholder:text-fg-4"
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <CategoryChip active={!category} onClick={() => setCategory(null)} label={s.all} count={total} />
        {ORDER.filter((c) => counts[c]).map((c) => {
          const Icon = ICONS[c];
          return (
            <CategoryChip key={c} active={category === c} onClick={() => setCategory(c)} label={s.categories[c]}
                          count={counts[c]} icon={<Icon className="size-4" />} />  // prettier-ignore
          );
        })}
      </div>

      {error && <p className="mt-6 rounded-2xl bg-danger/10 p-4 text-sm text-danger">{error}</p>}
      {sounds === null ? (
        <div className="mt-6 flex flex-col gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="shimmer h-20 rounded-2xl" />
          ))}
        </div>
      ) : shown.length === 0 ? (
        <p className="mt-16 text-center text-fg-3">{s.empty}</p>
      ) : (
        <div className="mt-6 flex flex-col gap-8">
          {groups.map(([c, list]) => {
            const Icon = ICONS[c];
            return (
              <section key={c || "all"}>
                {c && (
                  <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-fg-2 uppercase">
                    {Icon && <Icon className="size-4 text-lime" />} {s.categories[c]}
                    <span className="font-normal text-fg-3">· {list.length}</span>
                  </h2>
                )}
                <ul className="flex flex-col gap-2">
                  {list.map((x) => (
                    <SoundRow key={x.id} sound={x} playing={playing === x.id} onToggle={() => toggle(x)} onUpdate={update}
                              locale={locale} />  // prettier-ignore
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CategoryChip({ active, onClick, label, count, icon }: {
  active: boolean; onClick: () => void; label: string; count: number; icon?: React.ReactNode;
}) {  // prettier-ignore
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex h-10 items-center gap-2 rounded-xl px-3.5 text-[14px] font-medium transition-colors",
        active ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg-2",
      )}
    >
      {icon}
      {label}
      <span className="font-mono text-xs text-fg-3">{count}</span>
    </button>
  );
}

function SoundRow({ sound, playing, onToggle, onUpdate, locale }: {
  sound: Sound; playing: boolean; onToggle: () => void; locale: string;
  onUpdate: (id: string, patch: { title?: string; category?: string; tags?: string[] }) => Promise<void>;
}) {  // prettier-ignore
  const s = useI18n().t.sounds;
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(sound.title);
  const [tag, setTag] = useState("");
  const [copied, setCopied] = useState(false);

  async function saveTitle() {
    setEditing(false);
    if (title.trim() && title.trim() !== sound.title) await onUpdate(sound.id, { title: title.trim() });
    else setTitle(sound.title);
  }

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-surface-2 p-3">
      <button
        type="button"
        onClick={onToggle}
        aria-label={sound.title}
        className={clsx(
          "flex size-11 shrink-0 items-center justify-center rounded-xl transition-colors",
          playing ? "bg-lime text-ink" : "bg-glass text-fg hover:bg-white/10",
        )}
      >
        {playing ? <Pause className="size-5" /> : <Play className="size-5" />}
      </button>

      <div className="min-w-0 flex-1 basis-60">
        {editing ? (
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={saveTitle}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className="w-full rounded-md bg-surface-4 px-2 py-1 text-[15px] font-semibold outline-none"
          />
        ) : (
          <button type="button" onClick={() => setEditing(true)} title={s.rename} className="block max-w-full truncate text-left text-[15px] font-semibold hover:text-lime">
            {sound.title}
          </button>
        )}
        <p className="mt-0.5 truncate text-xs text-fg-3">
          {[s.kinds[sound.kind], seconds(sound.duration), s.origins[sound.origin], sound.source,
            new Date(sound.created_at).toLocaleDateString(locale)].filter(Boolean).join(" · ")}
        </p>{/* prettier-ignore */}
        <div className="mt-1.5 flex flex-wrap items-center gap-1">
          {sound.tags.map((x) => (
            <span key={x} className="flex items-center gap-1 rounded-md bg-glass px-1.5 py-0.5 text-[11px] text-fg-2">
              {x}
              <button type="button" aria-label={`× ${x}`} onClick={() => onUpdate(sound.id, { tags: sound.tags.filter((y) => y !== x) })} className="text-fg-3 hover:text-fg">
                <X className="size-3" />
              </button>
            </span>
          ))}
          <input
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && tag.trim()) {
                void onUpdate(sound.id, { tags: [...sound.tags, tag.trim()] });
                setTag("");
              }
            }}
            placeholder={s.addTag}
            className="w-24 rounded-md bg-transparent px-1 text-[11px] outline-none placeholder:text-fg-4 focus:bg-surface-4"
          />
        </div>
      </div>

      <select
        value={sound.category}
        onChange={(e) => onUpdate(sound.id, { category: e.target.value })}
        aria-label={s.category}
        className="rounded-lg bg-surface-4 px-2 py-2 text-xs font-semibold outline-none"
      >
        {ORDER.map((c) => (
          <option key={c} value={c}>
            {s.categories[c]}
          </option>
        ))}
      </select>

      <div className="flex items-center gap-1">
        {sound.text && (
          <RowButton label={s.copyText} onClick={() => {
            void navigator.clipboard.writeText(sound.text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}>
            {copied ? <Check className="size-4 text-lime" /> : <Copy className="size-4" />}
          </RowButton>
        )}{/* prettier-ignore */}
        <a href={`${BASE}${sound.file_url}`} download title={s.download} aria-label={s.download} className={ROW_BUTTON}>
          <Download className="size-4" />
        </a>
        {sound.job_id && (
          <Link href={`/history/${sound.job_id}`} title={s.open} aria-label={s.open} className={ROW_BUTTON}>
            <ExternalLink className="size-4" />
          </Link>
        )}
      </div>
    </li>
  );
}

const ROW_BUTTON = "flex size-8 items-center justify-center rounded-lg bg-glass text-fg-2 transition-colors hover:bg-white/10 hover:text-fg";

function RowButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" title={label} aria-label={label} onClick={onClick} className={ROW_BUTTON}>
      {children}
    </button>
  );
}

