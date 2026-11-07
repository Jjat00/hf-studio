"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, Clapperboard, Gauge, History, RotateCcw, Wand2 } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { ERAS, GENRES, PACINGS, findOption, type CinemaKey, type Option } from "./data";
import { CinemaModal, GhostButton, ModalTab, PrimaryButton } from "./previews";

type Props = {
  keys: CinemaKey[];
  values: Record<string, unknown>;
  setValue: (key: string, v: unknown) => void;
  onClose: () => void;
};

const FILM_TABS = [
  { key: "genre", icon: Clapperboard, list: GENRES },
  { key: "era", icon: History, list: ERAS },
  { key: "pacing", icon: Gauge, list: PACINGS },
] as const;

export function FilmModal({ keys, values, setValue, onClose }: Props) {
  const { t, pick } = useI18n();
  const tabs = FILM_TABS.filter((tb) => keys.includes(tb.key));
  const [tab, setTab] = useState<string>(tabs[0]?.key ?? "genre");
  const current = tabs.find((tb) => tb.key === tab) ?? tabs[0];
  const label = { genre: t.cinema.genre, era: t.cinema.era, pacing: t.cinema.tempo };
  const hint = { genre: t.cinema.genreHint, era: t.cinema.eraHint, pacing: t.cinema.tempoHint };
  const shown = (key: string, list: readonly Option[]) => {
    const o = findOption([...list], values[key]);
    return o ? pick(o.label) : t.cinema.auto;
  };

  return (
    <CinemaModal
      title={t.cinema.filmSetup}
      onClose={onClose}
      closeLabel={t.cinema.close}
      tabs={tabs.map((tb) => (
        <ModalTab
          key={tb.key}
          active={tb.key === current?.key}
          onClick={() => setTab(tb.key)}
          icon={<tb.icon className="size-4 shrink-0" />}
          label={label[tb.key]}
          value={shown(tb.key, tb.list)}
        />
      ))}
      footer={
        <>
          <GhostButton onClick={() => tabs.forEach((tb) => setValue(tb.key, undefined))}>
            <RotateCcw className="size-3.5" /> {t.cinema.resetAll}
          </GhostButton>
          <span className="flex-1" />
          <PrimaryButton onClick={onClose}>{t.cinema.done}</PrimaryButton>
        </>
      }
    >
      {current && (
        <>
          <p className="text-[18px] font-semibold">{label[current.key]}</p>
          <p className="mb-4 text-sm text-fg-3">{hint[current.key]}</p>
          {current.key === "era" ? (
            <EraRuler value={values.era as string | undefined} onChange={(v) => setValue("era", v)} />
          ) : (
            <Carousel list={[...current.list]} value={values[current.key] as string | undefined} onChange={(v) => setValue(current.key, v)} />
          )}
        </>
      )}
    </CinemaModal>
  );
}

/** Carrusel con «Auto» primero: anterior/siguiente cambian el valor y la vista grande muestra la opción. */
function Carousel({ list, value, onChange }: { list: Option[]; value?: string; onChange: (v: string | undefined) => void }) {
  const { t, pick } = useI18n();
  const items: (Option | null)[] = [null, ...list];
  const index = Math.max(0, items.findIndex((o) => (o ? o.value === value : value === undefined)));
  const go = (i: number) => onChange(items[(i + items.length) % items.length]?.value);
  const cur = items[index];
  const Icon = cur?.icon ?? Wand2;
  return (
    <div>
      <div className="flex items-stretch gap-2">
        <NavButton onClick={() => go(index - 1)} label={t.cinema.prev}>
          <ChevronLeft className="size-5" />
        </NavButton>
        <div
          className={clsx(
            "grain relative flex h-56 min-w-0 flex-1 flex-col items-center justify-center overflow-hidden rounded-2xl border border-line bg-gradient-to-br px-6 text-center",
            cur?.tone ?? "from-surface-5 via-surface-3 to-surface-2",
          )}
        >
          <Icon className="size-14 text-white/90 drop-shadow" strokeWidth={1.4} />
          <p className="headline mt-3 text-[30px] text-lime drop-shadow">{cur ? pick(cur.label) : t.cinema.auto}</p>
          {cur && <p className="mt-1 max-w-sm text-sm text-white/80">{pick(cur.desc)}</p>}
        </div>
        <NavButton onClick={() => go(index + 1)} label={t.cinema.next}>
          <ChevronRight className="size-5" />
        </NavButton>
      </div>
      <div className="mt-3 flex flex-wrap justify-center gap-1.5">
        {items.map((o, i) => (
          <button
            key={o?.value ?? "auto"}
            type="button"
            onClick={() => go(i)}
            className={clsx(
              "flex h-8 items-center gap-1.5 rounded-lg border-2 px-2.5 text-xs font-semibold transition-colors",
              i === index ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg hover:bg-white/10",
            )}
          >
            {o ? <o.icon className="size-3.5" /> : <Wand2 className="size-3.5" />}
            {o ? pick(o.label) : t.cinema.auto}
          </button>
        ))}
      </div>
    </div>
  );
}

function NavButton({ onClick, label, children }: { onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} className="flex w-10 shrink-0 items-center justify-center rounded-2xl border border-line bg-surface-3 text-fg-2 hover:bg-surface-4 hover:text-fg">
      {children}
    </button>
  );
}

const DECADES = [1960, 1970, 1980, 1990, 2000, 2010, 2020];

/** Regla de tiempo de 1960 a 2020: cada época es una marca; «Auto» va aparte, a la izquierda. */
function EraRuler({ value, onChange }: { value?: string; onChange: (v: string | undefined) => void }) {
  const { t, pick } = useI18n();
  const cur = findOption(ERAS, value);
  const pos = (era: string) => ((parseInt(era, 10) - 1960) / 60) * 100;
  return (
    <div>
      <div className="mb-5 flex min-h-24 flex-col items-center justify-center text-center">
        <p className="headline text-[44px] leading-none text-lime">{cur ? pick(cur.label) : t.cinema.auto}</p>
        <p className="mt-2 text-sm text-fg-2">{cur ? pick(cur.desc) : " "}</p>
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange(undefined)}
          className={clsx(
            "h-9 shrink-0 rounded-xl border-2 px-3 text-xs font-semibold",
            !cur ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg hover:bg-white/10",
          )}
        >
          {t.cinema.auto}
        </button>
        <div className="relative h-20 flex-1 px-3">
          <div className="relative h-full">
            {/* marcas menores cada dos años */}
            {Array.from({ length: 31 }, (_, i) => (
              <span
                key={i}
                aria-hidden
                className={clsx("absolute top-6 w-px -translate-x-1/2", i % 5 === 0 ? "h-5 bg-fg-3" : "h-2.5 bg-fg-4")}
                style={{ left: `${(i / 30) * 100}%` }}
              />
            ))}
            {DECADES.map((d) => (
              <span key={d} aria-hidden className="absolute top-12 -translate-x-1/2 font-mono text-[10px] text-fg-4" style={{ left: `${((d - 1960) / 60) * 100}%` }}>
                {String(d).slice(2)}
              </span>
            ))}
            {ERAS.map((e) => {
              const active = e.value === value;
              return (
                <button
                  key={e.value}
                  type="button"
                  onClick={() => onChange(e.value)}
                  aria-label={pick(e.label)}
                  className="group absolute top-0 flex -translate-x-1/2 flex-col items-center"
                  style={{ left: `${pos(e.value)}%` }}
                >
                  <span className={clsx("block rounded-full transition-all", active ? "size-5 bg-lime shadow-[0_0_14px_rgba(209,254,23,0.6)]" : "size-3.5 bg-surface-5 ring-2 ring-fg-3 group-hover:ring-fg")} />
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-5 gap-1.5">
        {ERAS.map((e) => (
          <button
            key={e.value}
            type="button"
            onClick={() => onChange(e.value)}
            className={clsx(
              "flex flex-col items-center gap-1 rounded-xl border-2 px-1 py-2 text-[11px] font-semibold",
              e.value === value ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg-2 hover:bg-white/10",
            )}
          >
            <e.icon className="size-4" />
            {e.value}
          </button>
        ))}
      </div>
    </div>
  );
}
