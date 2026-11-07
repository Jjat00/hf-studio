"use client";

import clsx from "clsx";
import { useEffect, useState, type Dispatch, type ReactNode, type RefObject, type SetStateAction } from "react";
import { useI18n } from "@/components/i18n-provider";
import {
  APERTURES,
  CARD_IMAGES,
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
import { CinemaImg, LightSphere, PaletteMosaic, PaletteStrip } from "./previews";

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

export type CinemaPanel = "film" | "camera" | "palette" | "light";

type ControlsProps = CinemaProps & {
  /** `grid`: tarjetas en rejilla (Video). `row`: una fila, como el compositor de Cinema Studio. */
  variant?: "grid" | "row";
  /** Nombres de las tarjetas (Cinema Studio usa los de Higgsfield). */
  names?: { film: string; camera: string; palette: string; light: string };
  /** Tarjeta al principio de la fila (References). */
  lead?: ReactNode;
  /** Ventana abierta, controlada desde fuera (p. ej. el botón de movimiento del compositor). */
  open?: CinemaPanel | null;
  onOpenChange?: (panel: CinemaPanel | null) => void;
  cameraTab?: "setup" | "movement";
};

/** Barra de dirección de Cinema Studio: película, cámara, paleta e iluminación, cada una con su ventana. */
export function CinemaControls(props: ControlsProps) {
  const { keys, values, setValue, extra, setExtra, variant = "grid", lead } = props;
  const { t, pick } = useI18n();
  const [ownOpen, setOwnOpen] = useState<CinemaPanel | null>(null);
  const open = props.open !== undefined ? props.open : ownOpen;
  const setOpen = props.onOpenChange ?? setOwnOpen;
  const names = props.names ?? { film: t.cinema.filmSetup, camera: t.cinema.camera, palette: t.cinema.palette, light: t.cinema.lighting };
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

  const paletteName = catalogPalette?.name ?? palette?.name ?? t.cinema.auto;
  const lightName = scheme ? pick(scheme.label) : (lighting?.name ?? t.cinema.auto);

  // Miniaturas de las tarjetas: la foto de la opción elegida o, en Auto, la de la tarjeta (como Higgsfield).
  const img = (src: string, fit: "cover" | "contain" = "cover") => <CinemaImg src={src} fit={fit} className={clsx("size-full", fit === "contain" && "p-0.5")} />;
  const filmPick = [findOption(GENRES, values.genre), findOption(ERAS, values.era), findOption(PACINGS, values.pacing)].find(Boolean);
  const gearPick = [findOption(LENSES, values.camera_lens), findOption(CAMERAS, values.camera_model), findOption(APERTURES, values.camera_aperture)].find(Boolean);
  const thumbs = {
    film: img(filmPick?.image ?? CARD_IMAGES.film, filmPick?.image ? "cover" : "contain"),
    camera: firstMove?.image ? img(firstMove.image) : img(gearPick?.image ?? CARD_IMAGES.camera, "contain"),
    palette: paletteColors ? <PaletteMosaic colors={paletteColors} className="size-full" /> : img(CARD_IMAGES.palette, "contain"),
    light: scheme?.image ? img(scheme.image) : sphere ? <LightSphere {...sphere} size={30} /> : img(CARD_IMAGES.light, "contain"),
  };

  return (
    // En la fila del compositor sin @container: la contención haría de esta caja el ancla de las ventanas.
    <div className={clsx("flex flex-col gap-2", variant === "grid" && "@container")}>
      {variant === "row" ? (
      <div className="hide-scrollbar flex gap-1.5 overflow-x-auto">
        {lead}
        {hasFilm && <RowCard thumb={thumbs.film} label={names.film} value={filmValue} active={filmValue !== t.cinema.auto} selected={open === "film"} onClick={() => setOpen("film")} />}
        {hasCamera && <RowCard thumb={thumbs.camera} label={names.camera} value={cameraValue} active={cameraValue !== t.cinema.auto} selected={open === "camera"} onClick={() => setOpen("camera")} />}
        {hasPalette && (
          <RowCard
            thumb={thumbs.palette}
            label={names.palette}
            value={paletteName}
            active={!!paletteColors}
            selected={open === "palette"}
            onClick={() => setOpen("palette")}
          />
        )}
        {hasLight && (
          <RowCard
            thumb={thumbs.light}
            label={names.light}
            value={lightName}
            active={!!sphere}
            selected={open === "light"}
            onClick={() => setOpen("light")}
          />
        )}
      </div>
      ) : (
      <div className="grid grid-cols-2 gap-2 @sm:grid-cols-4">
        {hasFilm && <Card thumb={thumbs.film} label={t.cinema.filmSetup} value={filmValue} active={filmValue !== t.cinema.auto} onClick={() => setOpen("film")} />}
        {hasCamera && <Card thumb={thumbs.camera} label={t.cinema.camera} value={cameraValue} active={cameraValue !== t.cinema.auto} onClick={() => setOpen("camera")} />}
        {hasPalette && (
          <Card
            thumb={thumbs.palette}
            label={t.cinema.palette}
            value={catalogPalette?.name ?? palette?.name ?? t.cinema.auto}
            active={!!paletteColors}
            onClick={() => setOpen("palette")}
            visual={paletteColors && <PaletteStrip colors={paletteColors} className="mt-1.5 h-1.5 w-full rounded-full" />}
          />
        )}
        {hasLight && (
          <Card
            thumb={thumbs.light}
            label={t.cinema.lighting}
            value={scheme ? pick(scheme.label) : (lighting?.name ?? t.cinema.auto)}
            active={!!sphere}
            onClick={() => setOpen("light")}
          />
        )}
      </div>
      )}

      {movements.length > 1 && <Sequence compact movements={movements} setMovements={setMovements} />}

      {variant === "grid" && extras.length > 0 && (
        <p className="rounded-xl border border-dashed border-line px-3 py-2 text-[11.5px] leading-snug text-fg-3">
          <span className="text-fg-2">{t.cinema.appended}</span> {extras.join(" ")}
        </p>
      )}

      {open === "film" && <FilmModal keys={keys} values={values} setValue={setValue} onClose={() => setOpen(null)} />}
      {open === "camera" && (
        <CameraModal keys={keys} values={values} setValue={setValue} movements={movements} setMovements={setMovements} initialTab={props.cameraTab} onClose={() => setOpen(null)} />
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

/** Tarjeta de la fila del compositor: miniatura, etiqueta pequeña en mono y el valor. */
function RowCard({ thumb, label, value, active, selected, onClick }: { thumb: ReactNode; label: string; value: string; active: boolean; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex h-12 min-w-[132px] flex-1 items-center gap-2.5 rounded-xl border py-1.5 pr-3 pl-1.5 text-left transition-colors hover:bg-surface-4",
        selected ? "border-line-2 bg-surface-4" : "border-transparent bg-surface-3",
      )}
    >
      <span className={clsx("flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-5", active ? "text-lime" : "text-fg-2")}>{thumb}</span>
      <span className="min-w-0">
        <span className="block truncate font-mono text-[10px] leading-tight text-fg-3">{label}</span>
        <span className={clsx("block truncate text-[14px] leading-tight font-semibold", active ? "text-fg" : "text-fg-2")}>{value}</span>
      </span>
    </button>
  );
}

function Card({ thumb, label, value, active, onClick, visual }: { thumb: ReactNode; label: string; value: string; active: boolean; onClick: () => void; visual?: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex min-w-0 items-center gap-2.5 rounded-2xl border bg-surface-3 py-2 pr-3 pl-2 text-left transition-colors hover:bg-surface-4",
        active ? "border-lime/40" : "border-line",
      )}
    >
      <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-5">{thumb}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] text-fg-3">{label}</span>
        <span className={clsx("block truncate text-[14px] font-semibold", active ? "text-fg" : "text-fg-2")}>{value}</span>
        {visual}
      </span>
    </button>
  );
}

type HashQuery = { start: number; end: number; text: string };

/** Menú que aparece al escribir # en el prompt: el movimiento elegido se añade a la secuencia y el #texto se quita. */
export function HashMovementMenu({ textareaRef, above, ...props }: CinemaProps & { textareaRef: RefObject<HTMLTextAreaElement | null>; above?: boolean }) {
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
    <div className={clsx("absolute inset-x-3 z-30 overflow-hidden rounded-2xl border border-line-2 bg-surface-2 p-1 shadow-2xl", above ? "bottom-full mb-1" : "top-full mt-1")}>
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
          {m.image ? <CinemaImg src={m.image} className="size-7 shrink-0 rounded-md" /> : <m.icon className="size-4 shrink-0 text-fg-2" />}
          <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{pick(m.label)}</span>
          {movements.includes(m.value) && <span className="text-[11px] text-lime">{movements.indexOf(m.value) + 1}</span>}
        </button>
      ))}
    </div>
  );
}
