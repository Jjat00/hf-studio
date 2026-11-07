"use client";

import clsx from "clsx";
import { ArrowDownAZ, Camera, LayoutGrid, Move3d, RotateCcw, Search, Wand2, X } from "lucide-react";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { APERTURES, CAMERAS, LENSES, MOVEMENTS, findOption, type CinemaKey, type Movement, type MovementGroup, type Option } from "./data";
import { ApertureBar, CinemaImg, CinemaModal, GhostButton, ModalTab, PrimaryButton } from "./previews";

type Props = {
  keys: CinemaKey[];
  values: Record<string, unknown>;
  setValue: (key: string, v: unknown) => void;
  movements: string[];
  setMovements: (list: string[]) => void;
  initialTab?: "setup" | "movement";
  onClose: () => void;
};

const SETUP_KEYS = ["camera_model", "camera_lens", "camera_aperture"] as const;
const GROUPS: MovementGroup[] = ["pan", "dolly", "crane", "zoom", "special"];

export function CameraModal({ keys, values, setValue, movements, setMovements, initialTab, onClose }: Props) {
  const { t, pick } = useI18n();
  const hasSetup = SETUP_KEYS.some((k) => keys.includes(k));
  const hasMovement = keys.includes("camera_movement");
  const [tab, setTab] = useState<"setup" | "movement">(initialTab && (initialTab === "setup" ? hasSetup : hasMovement) ? initialTab : hasSetup ? "setup" : "movement");
  const setupValue = SETUP_KEYS.filter((k) => keys.includes(k))
    .map((k) => findOption([...CAMERAS, ...LENSES, ...APERTURES], values[k]))
    .filter(Boolean)
    .map((o) => pick(o!.label))
    .join(" · ");

  return (
    <CinemaModal
      wide
      title={t.cinema.camera}
      onClose={onClose}
      closeLabel={t.cinema.close}
      tabs={
        <>
          {hasSetup && <ModalTab active={tab === "setup"} onClick={() => setTab("setup")} icon={<Camera className="size-4 shrink-0" />} label={t.cinema.setup} value={setupValue || t.cinema.auto} />}
          {hasMovement && (
            <ModalTab
              active={tab === "movement"}
              onClick={() => setTab("movement")}
              icon={<Move3d className="size-4 shrink-0" />}
              label={t.cinema.movement}
              value={movements.length ? t.cinema.moves(movements.length) : t.cinema.auto}
            />
          )}
        </>
      }
      footer={
        <>
          <GhostButton
            onClick={() => {
              SETUP_KEYS.forEach((k) => keys.includes(k) && setValue(k, undefined));
              if (hasMovement) setMovements([]);
            }}
          >
            <RotateCcw className="size-3.5" /> {t.cinema.resetAll}
          </GhostButton>
          <span className="flex-1" />
          <PrimaryButton onClick={onClose}>{t.cinema.done}</PrimaryButton>
        </>
      }
    >
      {tab === "setup" ? <Setup keys={keys} values={values} setValue={setValue} /> : <Movements movements={movements} setMovements={setMovements} />}
    </CinemaModal>
  );
}

function Setup({ keys, values, setValue }: Pick<Props, "keys" | "values" | "setValue">) {
  const { t, pick } = useI18n();
  const cols = [
    { key: "camera_model", label: t.cinema.body, list: CAMERAS },
    { key: "camera_lens", label: t.cinema.lens, list: LENSES },
    { key: "camera_aperture", label: t.cinema.aperture, list: APERTURES },
  ].filter((c) => keys.includes(c.key as CinemaKey));
  return (
    <div>
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(0, 1fr))` }}>
        {cols.map((c) => (
          <Wheel key={c.key} label={c.label} list={c.list} value={values[c.key] as string | undefined} onChange={(v) => setValue(c.key, v)} />
        ))}
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {cols.map((c) => {
          const o = findOption(c.list, values[c.key]);
          return (
            <div key={c.key} className="rounded-2xl border border-line bg-surface-3 p-3">
              <p className="text-[12px] text-fg-3">{c.label}</p>
              <p className="text-[14px] font-semibold">{o ? pick(o.label) : t.cinema.auto}</p>
              <p className="mt-0.5 min-h-8 text-xs text-fg-2">{o ? pick(o.desc) : " "}</p>
              {c.key === "camera_aperture" && <ApertureBar value={o?.value} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const ROW = 96;

/** Columna tipo rueda, como la de Higgsfield: fichas redondeadas con la foto del producto y su nombre; la elegida
 * queda centrada y resaltada. «Auto» es la primera. */
function Wheel({ label, list, value, onChange }: { label: string; list: Option[]; value?: string; onChange: (v: string | undefined) => void }) {
  const { t, pick } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const items: (Option | null)[] = [null, ...list];
  const index = Math.max(0, items.findIndex((o) => (o ? o.value === value : value === undefined)));
  useLayoutEffect(() => {
    ref.current?.scrollTo({ top: index * ROW, behavior: "smooth" });
  }, [index]);
  return (
    <div className="min-w-0">
      <p className="mb-2 text-center text-[11px] font-semibold tracking-[0.14em] text-fg-3 uppercase">{label}</p>
      <div className="relative overflow-hidden rounded-2xl border border-line bg-surface-3">
        <div
          ref={ref}
          className="hide-scrollbar relative snap-y snap-mandatory overflow-y-auto [mask-image:linear-gradient(to_bottom,transparent,black_28%,black_72%,transparent)]"
          style={{ height: ROW * 3, paddingBlock: ROW }}
        >
          {items.map((o, i) => {
            const active = i === index;
            const Icon = o?.icon ?? Wand2;
            return (
              <div key={o?.value ?? "auto"} className="flex snap-center items-center justify-center px-1.5 sm:px-3" style={{ height: ROW }}>
                <button
                  type="button"
                  onClick={() => onChange(o?.value)}
                  aria-pressed={active}
                  className={clsx(
                    "flex h-[84px] w-full max-w-40 flex-col items-center justify-center gap-1 rounded-[30px] border-2 px-2 text-center transition-all",
                    active ? "border-fg bg-surface-5 text-fg" : "border-line bg-surface-4/60 text-fg-3 hover:text-fg-2",
                  )}
                >
                  {o?.image ? (
                    <CinemaImg src={o.image} fit="contain" className={clsx("h-11 w-full drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)] transition-opacity", !active && "opacity-60")} />
                  ) : (
                    <span className="flex h-11 items-center">
                      <Icon className="size-6" />
                    </span>
                  )}
                  <span className={clsx("w-full truncate text-[12px] leading-tight", active && "font-semibold")}>{o ? pick(o.label) : t.cinema.auto}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Movements({ movements, setMovements }: { movements: string[]; setMovements: (list: string[]) => void }) {
  const { t, pick } = useI18n();
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"group" | "az">("group");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = MOVEMENTS.filter((m) => !needle || [m.value, m.label.es, m.label.en, m.desc.es, m.desc.en].some((s) => s.toLowerCase().includes(needle)));
    return sort === "az" ? [...list].sort((a, b) => pick(a.label).localeCompare(pick(b.label))) : list;
  }, [q, sort, pick]);
  const toggle = (v: string) => setMovements(movements.includes(v) ? movements.filter((x) => x !== v) : [...movements, v]);

  return (
    <div>
      <p className="mb-3 text-sm text-fg-3">{t.cinema.movementHint}</p>
      <Sequence movements={movements} setMovements={setMovements} />
      <div className="mt-3 mb-3 flex items-center gap-2">
        <div className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-xl border border-line bg-surface-3 px-3">
          <Search className="size-4 shrink-0 text-fg-3" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.cinema.search} className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-fg-4" />
        </div>
        <GhostButton onClick={() => setSort(sort === "group" ? "az" : "group")}>
          {sort === "group" ? <LayoutGrid className="size-3.5" /> : <ArrowDownAZ className="size-3.5" />}
          {sort === "group" ? t.cinema.sortCatalog : t.cinema.sortAz}
        </GhostButton>
      </div>
      {sort === "group" && !q.trim() ? (
        GROUPS.map((g) => (
          <div key={g} className="mb-4">
            <p className="mb-2 text-[11px] font-semibold tracking-[0.14em] text-fg-3 uppercase">{t.cinema.groups[g]}</p>
            <TileGrid list={filtered.filter((m) => m.group === g)} movements={movements} onToggle={toggle} />
          </div>
        ))
      ) : (
        <TileGrid list={filtered} movements={movements} onToggle={toggle} />
      )}
    </div>
  );
}

function TileGrid({ list, movements, onToggle }: { list: Movement[]; movements: string[]; onToggle: (v: string) => void }) {
  const { pick } = useI18n();
  return (
    <div className="grid grid-cols-3 gap-x-2 gap-y-3 sm:grid-cols-4">
      {list.map((m) => {
        const n = movements.indexOf(m.value);
        return (
          <button
            key={m.value}
            type="button"
            onClick={() => onToggle(m.value)}
            title={pick(m.desc)}
            className="group relative flex flex-col items-center gap-1.5 text-center"
          >
            <span
              className={clsx(
                "block aspect-square w-full overflow-hidden rounded-2xl border-2 bg-surface-3 transition-colors",
                n >= 0 ? "border-lime" : "border-transparent group-hover:border-line-2",
              )}
            >
              {m.image ? (
                <CinemaImg src={m.image} className="size-full transition-transform duration-300 group-hover:scale-105" />
              ) : (
                <span className="flex size-full items-center justify-center text-fg-2">
                  <m.icon className="size-7" />
                </span>
              )}
            </span>
            <span className={clsx("w-full truncate text-[13px] leading-tight font-semibold", n >= 0 ? "text-lime" : "text-fg")}>{pick(m.label)}</span>
            {n >= 0 && <span className="absolute top-2 right-2 flex size-6 items-center justify-center rounded-full bg-lime text-[12px] font-bold text-ink shadow">{n + 1}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Movimientos elegidos en orden, con su número; cada uno se puede quitar. */
export function Sequence({ movements, setMovements, compact }: { movements: string[]; setMovements: (list: string[]) => void; compact?: boolean }) {
  const { t, pick } = useI18n();
  if (!movements.length) return compact ? null : <p className="rounded-xl border border-dashed border-line px-3 py-2.5 text-sm text-fg-3">{t.cinema.noMovements}</p>;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {!compact && <span className="mr-1 text-[12px] text-fg-3">{t.cinema.sequence}</span>}
      {movements.map((v, i) => {
        const m = MOVEMENTS.find((x) => x.value === v);
        return (
          <span key={v} className="flex h-8 items-center gap-1.5 rounded-lg bg-lime/10 pr-1 pl-1.5 text-xs font-semibold text-lime">
            <span className="flex size-5 items-center justify-center rounded-full bg-lime text-[11px] text-ink">{i + 1}</span>
            {m ? pick(m.label) : v}
            <button type="button" aria-label={t.cinema.remove} onClick={() => setMovements(movements.filter((x) => x !== v))} className="rounded p-0.5 text-lime/70 hover:bg-lime/15 hover:text-lime">
              <X className="size-3.5" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
