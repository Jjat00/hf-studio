"use client";

import clsx from "clsx";
import { Check, Plus, Save, Trash2, Wand2, X } from "lucide-react";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { LIGHTS, LIGHTS_KEY, LIGHT_DIRECTIONS, MAX_LIGHTS, loadStored, newId, saveStored, type CustomLighting, type LightSource } from "./data";
import { Hex } from "./palette-modal";
import { CinemaImg, CinemaModal, GhostButton, LightSphere, PrimaryButton } from "./previews";

type Props = {
  value?: string;
  custom: CustomLighting | null;
  /** Esquema del catálogo (string), iluminación propia (objeto) o Auto (null). */
  onPick: (p: string | CustomLighting | null) => void;
  onClose: () => void;
};

export function LightingModal({ value, custom, onPick, onClose }: Props) {
  const { t, pick: tr } = useI18n();
  const [saved, setSaved] = useState<CustomLighting[]>(() => loadStored<CustomLighting>(LIGHTS_KEY));
  const [editing, setEditing] = useState(false);

  const pick = (p: string | CustomLighting | null) => {
    onPick(p);
    onClose();
  };
  const persist = (next: CustomLighting[]) => {
    setSaved(next);
    saveStored(LIGHTS_KEY, next);
  };

  return (
    <CinemaModal wide title={editing ? t.cinema.newLighting : t.cinema.lighting} onClose={onClose} closeLabel={t.cinema.close}>
      {editing ? (
        <LightingEditor
          onCancel={() => setEditing(false)}
          onApply={pick}
          onSave={(p) => {
            persist([p, ...saved]);
            pick(p);
          }}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line-2 text-fg-2 transition-colors hover:border-lime/60 hover:text-lime"
          >
            <Plus className="size-6" />
            <span className="text-[13px] font-semibold">{t.cinema.newLighting}</span>
          </button>
          <button
            type="button"
            onClick={() => pick(null)}
            className={clsx(
              "flex min-h-40 flex-col items-center justify-center gap-2 rounded-2xl border-2 bg-surface-3 transition-colors",
              !value && !custom ? "border-lime/70 text-lime" : "border-transparent text-fg-2 hover:bg-surface-4",
            )}
          >
            <Wand2 className="size-6" />
            <span className="text-[13px] font-semibold">{t.cinema.auto}</span>
          </button>
          {saved.map((p) => (
            <div key={p.id} className="group relative">
              <SchemeTile name={p.name} lights={p.lights} active={custom?.id === p.id} onClick={() => pick(p)} />
              <button
                type="button"
                aria-label={t.cinema.delete}
                onClick={() => {
                  persist(saved.filter((x) => x.id !== p.id));
                  if (custom?.id === p.id) onPick(null);
                }}
                className="absolute top-2 right-2 rounded-lg bg-black/60 p-1 text-white/80 backdrop-blur hover:text-danger sm:opacity-0 sm:group-hover:opacity-100"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
          {LIGHTS.map((s) => (
            <SchemeTile key={s.value} name={tr(s.label)} desc={tr(s.desc)} image={s.image} {...s.preview} active={value === s.value} onClick={() => pick(s.value)} />
          ))}
        </div>
      )}
    </CinemaModal>
  );
}

function SchemeTile({ name, desc, image, lights, backdrop, dark, active, onClick }: { name: string; desc?: string; image?: string; lights: LightSource[]; backdrop?: string; dark?: boolean; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx("flex w-full flex-col overflow-hidden rounded-2xl border-2 bg-surface-3 text-left transition-colors", active ? "border-lime/80" : "border-transparent hover:border-line-2")}
    >
      {image ? (
        <CinemaImg src={image} className="h-28 w-full" />
      ) : (
        <LightSphere lights={lights} backdrop={backdrop ?? "#0e0f11"} dark={dark} size={64} className="h-28 w-full rounded-none" />
      )}
      <span className="px-2.5 pt-2 pb-2.5">
        <span className="flex items-center gap-1.5 text-[13px] font-semibold">
          {active && <Check className="size-3.5 shrink-0 text-lime" />}
          <span className="truncate">{name}</span>
        </span>
        {desc && <span className="mt-0.5 line-clamp-2 block text-[11px] leading-snug text-fg-3">{desc}</span>}
      </span>
    </button>
  );
}

const NEW_LIGHT: LightSource = { color: "#ffb070", brightness: 70, diffuse: 60, direction: "left" };

function LightingEditor({ onCancel, onApply, onSave }: { onCancel: () => void; onApply: (p: CustomLighting) => void; onSave: (p: CustomLighting) => void }) {
  const { t } = useI18n();
  const [lights, setLights] = useState<LightSource[]>([NEW_LIGHT]);
  const [sel, setSel] = useState(0);
  const [name, setName] = useState("");
  const cur = lights[sel] ?? lights[0];
  const patch = (p: Partial<LightSource>) => setLights((ls) => ls.map((l, i) => (i === sel ? { ...l, ...p } : l)));
  const build = (): CustomLighting => ({ id: newId(), name: name.trim() || t.cinema.lightingName, lights });

  return (
    <div className="grid gap-5 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div>
        <div className="mb-4 flex flex-wrap items-center gap-1.5">
          {lights.map((l, i) => (
            <span key={i} className={clsx("flex h-8 items-center gap-1.5 rounded-lg border-2 pr-1 pl-2 text-xs font-semibold", i === sel ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg")}>
              <button type="button" onClick={() => setSel(i)} className="flex items-center gap-1.5">
                <span className="size-3 rounded-full" style={{ background: l.color }} />
                {t.cinema.lightN(i + 1)}
              </button>
              {lights.length > 1 && (
                <button
                  type="button"
                  aria-label={t.cinema.remove}
                  onClick={() => {
                    setLights((ls) => ls.filter((_, j) => j !== i));
                    setSel((s) => Math.max(0, s >= i ? s - 1 : s));
                  }}
                  className="rounded p-0.5 opacity-70 hover:opacity-100"
                >
                  <X className="size-3" />
                </button>
              )}
            </span>
          ))}
          {lights.length < MAX_LIGHTS && (
            <GhostButton
              className="h-8"
              onClick={() => {
                setLights((ls) => [...ls, { ...NEW_LIGHT, color: "#b9d4ff", direction: "right", brightness: 45 }]);
                setSel(lights.length);
              }}
            >
              <Plus className="size-3.5" /> {t.cinema.addLight}
            </GhostButton>
          )}
        </div>

        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface-3 p-4">
          <div className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-[13px] text-fg-3">{t.cinema.color}</span>
            <input type="color" value={cur.color} onChange={(e) => patch({ color: e.target.value })} className="size-8 cursor-pointer rounded-lg border border-line bg-transparent" />
            <div className="w-24">
              <Hex value={cur.color} onChange={(color) => patch({ color })} />
            </div>
          </div>
          <Slider label={t.cinema.brightness} value={cur.brightness} onChange={(brightness) => patch({ brightness })} />
          <Slider label={t.cinema.diffuse} value={cur.diffuse} onChange={(diffuse) => patch({ diffuse })} />
          <div>
            <p className="mb-2 text-[13px] text-fg-3">{t.cinema.direction}</p>
            <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6">
              {LIGHT_DIRECTIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => patch({ direction: d })}
                  className={clsx(
                    "h-8 rounded-lg border-2 text-xs font-semibold",
                    cur.direction === d ? "border-lime/70 bg-lime/10 text-lime" : "border-transparent bg-glass text-fg hover:bg-white/10",
                  )}
                >
                  {t.cinema.directions[d]}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <LightSphere lights={lights} backdrop="#0b0c0e" size={150} className="aspect-square w-full border border-line" />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t.cinema.lightingName}
          aria-label={t.cinema.name}
          maxLength={40}
          className="h-9 rounded-xl border border-line bg-surface-3 px-3 text-sm outline-none placeholder:text-fg-4 focus:border-line-2"
        />
        <div className="flex flex-wrap items-center gap-2">
          <GhostButton onClick={onCancel}>{t.cinema.back}</GhostButton>
          <span className="flex-1" />
          <GhostButton onClick={() => onSave(build())}>
            <Save className="size-3.5" /> {t.cinema.saveAsPreset}
          </GhostButton>
          <PrimaryButton onClick={() => onApply(build())}>{t.cinema.apply}</PrimaryButton>
        </div>
      </div>
    </div>
  );
}

function Slider({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-[13px] text-fg-3">{label}</span>
      <input type="range" min={0} max={100} value={value} onChange={(e) => onChange(Number(e.target.value))} className="h-1 flex-1 cursor-pointer" />
      <span className="w-10 text-right text-[13px] font-semibold tabular-nums">{value}%</span>
    </label>
  );
}
