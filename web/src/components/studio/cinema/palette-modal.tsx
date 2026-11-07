"use client";

import clsx from "clsx";
import { Check, Dices, ImagePlus, Palette as PaletteIcon, Plus, Trash2, Wand2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import {
  MAX_PALETTE_COLORS,
  PALETTES,
  PALETTES_KEY,
  dominantColors,
  hslToHex,
  loadStored,
  newId,
  normalizeHex,
  randomPalette,
  saveStored,
  type CustomPalette,
} from "./data";
import { CinemaModal, GhostButton, PaletteMosaic, PaletteStrip, PrimaryButton } from "./previews";

type Props = {
  value?: string;
  custom: CustomPalette | null;
  /** Paleta del catálogo (string), propia (objeto) o Auto (null). */
  onPick: (p: string | CustomPalette | null) => void;
  onClose: () => void;
};

export function PaletteModal({ value, custom, onPick, onClose }: Props) {
  const { t } = useI18n();
  const [saved, setSaved] = useState<CustomPalette[]>(() => loadStored<CustomPalette>(PALETTES_KEY));
  const [editing, setEditing] = useState(false);

  const pick = (p: string | CustomPalette | null) => {
    onPick(p);
    onClose();
  };
  const remove = (id: string) => {
    const next = saved.filter((p) => p.id !== id);
    setSaved(next);
    saveStored(PALETTES_KEY, next);
    if (custom?.id === id) onPick(null);
  };

  return (
    <CinemaModal wide title={editing ? t.cinema.newPalette : t.cinema.palette} onClose={onClose} closeLabel={t.cinema.close}>
      {editing ? (
        <PaletteEditor
          onCancel={() => setEditing(false)}
          onSave={(p) => {
            const next = [p, ...saved];
            setSaved(next);
            saveStored(PALETTES_KEY, next);
            pick(p);
          }}
        />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-line-2 text-fg-2 transition-colors hover:border-lime/60 hover:text-lime"
          >
            <Plus className="size-6" />
            <span className="text-[13px] font-semibold">{t.cinema.newPalette}</span>
          </button>
          <button
            type="button"
            onClick={() => pick(null)}
            className={clsx(
              "flex aspect-[4/3] flex-col items-center justify-center gap-2 rounded-2xl border-2 bg-surface-3 transition-colors",
              !value && !custom ? "border-lime/70 text-lime" : "border-transparent text-fg-2 hover:bg-surface-4",
            )}
          >
            <Wand2 className="size-6" />
            <span className="text-[13px] font-semibold">{t.cinema.auto}</span>
          </button>
          {saved.map((p) => (
            <Tile key={p.id} name={p.name} colors={p.colors} active={custom?.id === p.id} onClick={() => pick(p)} onDelete={() => remove(p.id)} deleteLabel={t.cinema.delete} />
          ))}
          {PALETTES.map((p) => (
            <Tile key={p.value} name={p.name} colors={p.colors} active={value === p.value} onClick={() => pick(p.value)} />
          ))}
        </div>
      )}
    </CinemaModal>
  );
}

function Tile({ name, colors, active, onClick, onDelete, deleteLabel }: { name: string; colors: string[]; active: boolean; onClick: () => void; onDelete?: () => void; deleteLabel?: string }) {
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onClick}
        className={clsx("w-full overflow-hidden rounded-2xl border-2 bg-surface-3 text-left transition-colors", active ? "border-lime/80" : "border-transparent hover:border-line-2")}
      >
        <PaletteMosaic colors={colors} className="aspect-[16/9] w-full" />
        <PaletteStrip colors={colors} className="h-3 w-full" />
        <span className="flex items-center gap-1.5 px-2.5 py-2 text-[12.5px] font-semibold">
          {active && <Check className="size-3.5 shrink-0 text-lime" />}
          <span className="truncate">{name}</span>
        </span>
      </button>
      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          aria-label={deleteLabel}
          className="absolute top-2 right-2 rounded-lg bg-black/60 p-1 text-white/80 opacity-100 backdrop-blur hover:text-danger sm:opacity-0 sm:group-hover:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      )}
    </div>
  );
}

function PaletteEditor({ onCancel, onSave }: { onCancel: () => void; onSave: (p: CustomPalette) => void }) {
  const { t } = useI18n();
  const [source, setSource] = useState<"image" | "wheel">("image");
  const [colors, setColors] = useState<string[]>(() => randomPalette(8));
  const [sel, setSel] = useState(0);
  const [name, setName] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [light, setLight] = useState(0.5);
  const fileRef = useRef<HTMLInputElement>(null);

  const setColor = (i: number, c: string) => setColors((cs) => cs.map((x, j) => (j === i ? c : x)));

  function fromFile(file: File) {
    const url = URL.createObjectURL(file);
    setImage((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 96 / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const found = dominantColors(ctx.getImageData(0, 0, canvas.width, canvas.height).data);
      if (found.length) {
        setColors(found);
        setSel(0);
      }
      if (!name) setName(file.name.replace(/\.[^.]+$/, "").slice(0, 40));
    };
    img.src = url;
  }

  function onWheel(e: React.MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left - r.width / 2;
    const y = e.clientY - r.top - r.height / 2;
    const dist = Math.min(1, Math.hypot(x, y) / (r.width / 2));
    const hue = ((Math.atan2(y, x) * 180) / Math.PI + 90 + 360) % 360;
    setColor(sel, hslToHex(hue, dist, light));
  }

  return (
    <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <div>
        <div className="mb-3 grid grid-cols-2 gap-1 rounded-2xl border border-line bg-surface-3 p-1">
          {(["image", "wheel"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSource(s)}
              className={clsx("h-9 rounded-xl text-[13px] font-semibold", source === s ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg-2")}
            >
              {s === "image" ? t.cinema.fromImage : t.cinema.colorWheel}
            </button>
          ))}
        </div>
        {source === "image" ? (
          <div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && fromFile(e.target.files[0])} />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="relative flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border-2 border-dashed border-line-2 text-fg-2 hover:border-lime/60 hover:text-lime"
            >
              {image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={image} alt="" className="absolute inset-0 size-full object-cover" />
              ) : (
                <>
                  <ImagePlus className="size-7" />
                  <span className="text-[13px] font-semibold">{t.cinema.pickImage}</span>
                </>
              )}
            </button>
            <p className="mt-2 text-xs text-fg-3">{t.cinema.imageHint}</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <div
              role="presentation"
              onClick={onWheel}
              className="relative aspect-square w-full max-w-[240px] cursor-crosshair rounded-full"
              style={{
                background: `radial-gradient(circle, hsl(0 0% ${light * 100}%) 0%, transparent 70%), conic-gradient(from 0deg, hsl(0 90% ${light * 100}%), hsl(60 90% ${light * 100}%), hsl(120 90% ${light * 100}%), hsl(180 90% ${light * 100}%), hsl(240 90% ${light * 100}%), hsl(300 90% ${light * 100}%), hsl(360 90% ${light * 100}%))`,
              }}
            >
              <span className="absolute top-1/2 left-1/2 size-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-white/90 shadow-lg" style={{ background: colors[sel] }} />
            </div>
            <input type="range" min={0.08} max={0.92} step={0.01} value={light} onChange={(e) => setLight(Number(e.target.value))} className="h-1 w-full max-w-[240px] cursor-pointer" aria-label={t.cinema.brightness} />
            <label className="flex items-center gap-2 text-xs text-fg-3">
              <input type="color" value={colors[sel] ?? "#888888"} onChange={(e) => setColor(sel, e.target.value)} className="size-8 cursor-pointer rounded-lg border border-line bg-transparent" />
              {t.cinema.color}
            </label>
          </div>
        )}
      </div>

      <div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {colors.map((c, i) => (
            <div key={i} className={clsx("relative rounded-xl border-2 bg-surface-3 p-1.5", i === sel ? "border-lime/70" : "border-transparent")}>
              <button type="button" onClick={() => setSel(i)} className="block h-12 w-full rounded-lg" style={{ background: c }} aria-label={c} />
              <Hex value={c} onChange={(v) => setColor(i, v)} />
              {i === 0 && <span className="absolute top-2.5 left-2.5 rounded bg-black/60 px-1 text-[10px] font-semibold text-white">{t.cinema.main}</span>}
              {colors.length > 1 && (
                <button
                  type="button"
                  aria-label={t.cinema.remove}
                  onClick={() => {
                    setColors((cs) => cs.filter((_, j) => j !== i));
                    setSel((s) => Math.max(0, s >= i ? s - 1 : s));
                  }}
                  className="absolute top-2.5 right-2.5 rounded bg-black/60 p-0.5 text-white/80 hover:text-danger"
                >
                  <X className="size-3" />
                </button>
              )}
            </div>
          ))}
          {colors.length < MAX_PALETTE_COLORS && (
            <button
              type="button"
              aria-label={t.cinema.addColor}
              onClick={() => {
                setColors((cs) => [...cs, cs[cs.length - 1] ?? "#888888"]);
                setSel(colors.length);
              }}
              className="flex min-h-[86px] items-center justify-center rounded-xl border-2 border-dashed border-line-2 text-fg-3 hover:border-lime/60 hover:text-lime"
            >
              <Plus className="size-5" />
            </button>
          )}
        </div>
        <PaletteStrip colors={colors} className="mt-3 h-4 rounded-lg" />
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <GhostButton onClick={() => setColors(randomPalette(colors.length || 8))}>
            <Dices className="size-3.5" /> {t.cinema.random}
          </GhostButton>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t.cinema.paletteName}
            aria-label={t.cinema.name}
            maxLength={40}
            className="h-9 min-w-0 flex-1 rounded-xl border border-line bg-surface-3 px-3 text-sm outline-none placeholder:text-fg-4 focus:border-line-2"
          />
        </div>
        <div className="mt-4 flex items-center gap-2">
          <GhostButton onClick={onCancel}>{t.cinema.back}</GhostButton>
          <span className="flex-1" />
          <PrimaryButton onClick={() => onSave({ id: newId(), name: name.trim() || t.cinema.paletteName, colors })} disabled={!colors.length}>
            <PaletteIcon className="size-3.5" /> {t.cinema.savePalette}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

/** Campo HEX: se edita libre y solo se aplica cuando es un color válido. */
export function Hex({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <input
      value={draft ?? value}
      onChange={(e) => {
        setDraft(e.target.value);
        const hex = normalizeHex(e.target.value);
        if (hex) onChange(hex);
      }}
      onBlur={() => setDraft(null)}
      spellCheck={false}
      maxLength={7}
      className="mt-1 w-full bg-transparent text-center font-mono text-[11px] text-fg-2 uppercase outline-none"
    />
  );
}
