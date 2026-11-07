"use client";

import clsx from "clsx";
import { Camera, Clapperboard, Lightbulb, Palette } from "lucide-react";
import { useEffect, useState, type Dispatch, type RefObject, type SetStateAction } from "react";
import { useI18n } from "@/components/i18n-provider";
import {
  APERTURES,
  CAMERAS,
  ERAS,
  GENRES,
  LENSES,
  LIGHTS,
  MOVEMENTS,
  PACINGS,
  cinemaPromptExtras,
  customLightingOf,
  customPaletteOf,
  findOption,
  findPalette,
  movementsOf,
  type CinemaExtra,
  type CinemaKey,
  type CustomLighting,
  type CustomPalette,
} from "./data";
import { CameraModal, Sequence } from "./camera-modal";
import { FilmModal } from "./film-modal";
import { LightingModal } from "./lighting-modal";
import { PaletteModal } from "./palette-modal";
import { LightSphere, PaletteStrip } from "./previews";

export type CinemaProps = {
  keys: CinemaKey[];
  values: Record<string, unknown>;
  setValue: (key: string, v: unknown) => void;
  extra: CinemaExtra;
  setExtra: Dispatch<SetStateAction<CinemaExtra>>;
};

/** Pone la secuencia de movimientos: el primero va en `camera_movement`, el resto viaja en el prompt. */
function useSetMovements({ setValue, setExtra }: Pick<CinemaProps, "setValue" | "setExtra">) {
  return (list: string[]) => {
    setValue("camera_movement", list[0]);
    setExtra((e) => ({ ...e, movements: list }));
  };
}

/** Barra de dirección de Cinema Studio: película, cámara, paleta e iluminación, cada una con su ventana. */
export function CinemaControls(props: CinemaProps) {
  const { keys, values, setValue, extra, setExtra } = props;
  const { t, pick } = useI18n();
  const [open, setOpen] = useState<"film" | "camera" | "palette" | "light" | null>(null);
  const setMovements = useSetMovements(props);
  const movements = movementsOf(values, extra);
  const palette = customPaletteOf(values, extra);
  const lighting = customLightingOf(values, extra);
  const extras = cinemaPromptExtras(values, extra);

  const hasFilm = keys.some((k) => k === "genre" || k === "era" || k === "pacing");
  const hasCamera = keys.some((k) => k.startsWith("camera_"));
  const hasPalette = keys.includes("color_palette");
  const hasLight = keys.includes("light");

  const filmValue =
    [findOption(GENRES, values.genre), findOption(ERAS, values.era), findOption(PACINGS, values.pacing)]
      .filter(Boolean)
      .map((o) => pick(o!.label))
      .join(" · ") || t.cinema.auto;
  const firstMove = MOVEMENTS.find((m) => m.value === movements[0]);
  const setup = [findOption(CAMERAS, values.camera_model), findOption(LENSES, values.camera_lens), findOption(APERTURES, values.camera_aperture)].filter(Boolean);
  const cameraValue = firstMove
    ? `${pick(firstMove.label)}${movements.length > 1 ? ` +${movements.length - 1}` : ""}`
    : setup.length
      ? setup.map((o) => pick(o!.label)).join(" · ")
      : t.cinema.auto;
  const catalogPalette = findPalette(values.color_palette);
  const paletteColors = catalogPalette?.colors ?? palette?.colors;
  const scheme = findOption(LIGHTS, values.light) as (typeof LIGHTS)[number] | undefined;
  const sphere = scheme?.preview ?? (lighting ? { lights: lighting.lights } : null);

  return (
    <div className="@container flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2 @sm:grid-cols-4">
        {hasFilm && <Card icon={<Clapperboard className="size-4" />} label={t.cinema.filmSetup} value={filmValue} active={filmValue !== t.cinema.auto} onClick={() => setOpen("film")} />}
        {hasCamera && <Card icon={<Camera className="size-4" />} label={t.cinema.camera} value={cameraValue} active={cameraValue !== t.cinema.auto} onClick={() => setOpen("camera")} />}
        {hasPalette && (
          <Card
            icon={<Palette className="size-4" />}
            label={t.cinema.palette}
            value={catalogPalette?.name ?? palette?.name ?? t.cinema.auto}
            active={!!paletteColors}
            onClick={() => setOpen("palette")}
            visual={paletteColors && <PaletteStrip colors={paletteColors} className="mt-1.5 h-1.5 w-full rounded-full" />}
          />
        )}
        {hasLight && (
          <Card
            icon={sphere ? <LightSphere {...sphere} size={16} /> : <Lightbulb className="size-4" />}
            label={t.cinema.lighting}
            value={scheme ? pick(scheme.label) : (lighting?.name ?? t.cinema.auto)}
            active={!!sphere}
            onClick={() => setOpen("light")}
          />
        )}
      </div>

      {movements.length > 1 && <Sequence compact movements={movements} setMovements={setMovements} />}

      {extras.length > 0 && (
        <p className="rounded-xl border border-dashed border-line px-3 py-2 text-[11.5px] leading-snug text-fg-3">
          <span className="text-fg-2">{t.cinema.appended}</span> {extras.join(" ")}
        </p>
      )}

      {open === "film" && <FilmModal keys={keys} values={values} setValue={setValue} onClose={() => setOpen(null)} />}
      {open === "camera" && (
        <CameraModal keys={keys} values={values} setValue={setValue} movements={movements} setMovements={setMovements} onClose={() => setOpen(null)} />
      )}
      {open === "palette" && (
        <PaletteModal
          value={values.color_palette as string | undefined}
          custom={palette}
          onPick={(p: string | CustomPalette | null) => {
            setValue("color_palette", typeof p === "string" ? p : undefined);
            setExtra((e) => ({ ...e, palette: p && typeof p === "object" ? p : null }));
          }}
          onClose={() => setOpen(null)}
        />
      )}
      {open === "light" && (
        <LightingModal
          value={values.light as string | undefined}
          custom={lighting}
          onPick={(p: string | CustomLighting | null) => {
            setValue("light", typeof p === "string" ? p : undefined);
            setExtra((e) => ({ ...e, lighting: p && typeof p === "object" ? p : null }));
          }}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  );
}

function Card({ icon, label, value, active, onClick, visual }: { icon: React.ReactNode; label: string; value: string; active: boolean; onClick: () => void; visual?: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex min-w-0 flex-col rounded-2xl border bg-surface-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-4",
        active ? "border-lime/40" : "border-line",
      )}
    >
      <span className="flex items-center gap-1.5 text-[12px] text-fg-3">
        <span className={clsx("flex shrink-0 items-center", active && "text-lime")}>{icon}</span>
        <span className="truncate">{label}</span>
      </span>
      <span className={clsx("mt-0.5 truncate text-[14px] font-semibold", active ? "text-fg" : "text-fg-2")}>{value}</span>
      {visual}
    </button>
  );
}

type HashQuery = { start: number; end: number; text: string };

/** Menú que aparece al escribir # en el prompt: el movimiento elegido se añade a la secuencia y el #texto se quita. */
export function HashMovementMenu({ textareaRef, ...props }: CinemaProps & { textareaRef: RefObject<HTMLTextAreaElement | null> }) {
  const { values, setValue, extra } = props;
  const { t, pick } = useI18n();
  const [query, setQuery] = useState<HashQuery | null>(null);
  const [active, setActive] = useState(0);
  const setMovements = useSetMovements(props);
  const movements = movementsOf(values, extra);
  const needle = query?.text.toLowerCase() ?? "";
  const list = query
    ? MOVEMENTS.filter((m) => !needle || [m.value, m.label.es, m.label.en].some((s) => s.toLowerCase().includes(needle))).slice(0, 8)
    : [];
  const open = !!query && list.length > 0;

  function choose(value: string) {
    const el = textareaRef.current;
    if (!el || !query) return;
    const text = el.value;
    const next = (text.slice(0, query.start) + text.slice(query.end)).replace(/ {2,}/g, " ");
    setValue("prompt", next || undefined);
    if (!movements.includes(value)) setMovements([...movements, value]);
    setQuery(null);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(query.start, query.start);
    });
  }

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const check = () => {
      const caret = el.selectionStart ?? 0;
      if (caret !== el.selectionEnd) return setQuery(null);
      const m = /(?:^|\s)#([\p{L}\w-]*)$/u.exec(el.value.slice(0, caret));
      if (!m) return setQuery(null);
      setQuery((q) => {
        const nq = { start: caret - m[1].length - 1, end: caret, text: m[1] };
        if (!q || q.text !== nq.text) setActive(0);
        return nq;
      });
    };
    const onKey = (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => (a + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length);
      } else if ((e.key === "Enter" || e.key === "Tab") && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        choose(list[Math.min(active, list.length - 1)].value);
      } else if (e.key === "Escape") {
        e.preventDefault();
        setQuery(null);
      }
    };
    const close = () => setTimeout(() => setQuery(null), 150);
    el.addEventListener("input", check);
    el.addEventListener("click", check);
    el.addEventListener("keydown", onKey);
    el.addEventListener("blur", close);
    return () => {
      el.removeEventListener("input", check);
      el.removeEventListener("click", check);
      el.removeEventListener("keydown", onKey);
      el.removeEventListener("blur", close);
    };
  });

  if (!open) return null;
  return (
    <div className="absolute inset-x-3 top-full z-30 mt-1 overflow-hidden rounded-2xl border border-line-2 bg-surface-2 p-1 shadow-2xl">
      <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold tracking-[0.12em] text-fg-3 uppercase">{t.cinema.hashTitle}</p>
      {list.map((m, i) => (
        <button
          key={m.value}
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => choose(m.value)}
          onMouseEnter={() => setActive(i)}
          className={clsx("flex w-full items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-left", i === active ? "bg-surface-4" : "")}
        >
          <m.icon className="size-4 shrink-0 text-fg-2" />
          <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{pick(m.label)}</span>
          {movements.includes(m.value) && <span className="text-[11px] text-lime">{movements.indexOf(m.value) + 1}</span>}
        </button>
      ))}
    </div>
  );
}
