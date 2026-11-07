"use client";

import clsx from "clsx";
import {
  AtSign,
  Check,
  ChevronRight,
  Clock,
  Film,
  Gem,
  ImageIcon,
  Loader2,
  Minus,
  Music,
  Palette,
  Plus,
  ScanEye,
  Search,
  Sparkles,
  Video,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import { useI18n } from "@/components/i18n-provider";
import { RatioIcon } from "@/components/studio/controls";
import { StylePicker } from "@/components/studio/style-picker";
import { costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { CATEGORIES, elementMention } from "@/components/studio/element-refs";
import { CinemaControls, HashMovementMenu, type CinemaPanel } from "@/components/studio/cinema/cinema-controls";
import { EMPTY_CINEMA, applyCinema, cinemaKeysOf, type CinemaExtra } from "@/components/studio/cinema/data";
import { CinemaAnchorContext } from "@/components/studio/cinema/previews";
import { probeDuration } from "@/lib/media";
import { activeProject } from "@/lib/project";
import { cleanInput, defaultsFor, fieldsFor, type Field } from "@/lib/schema";
import { apiSrc, costShort, fieldErrors, formatUsd, modelLabel, outputSrc, studio, StudioError, type Estimate } from "@/lib/studio";
import type { ElementCategory, Generation, ModelDetail, ModelStyle, ModelSummary, StudioElement } from "@/lib/types";

type Mode = "video" | "image";
type MediaKind = "image" | "video" | "audio";
type MediaField = Extract<Field, { kind: "media" }>;
type Panel = "refs" | "style" | CinemaPanel;
type RefsTab = "uploads" | "elements" | "generations" | "liked";

const CINEMA_PREFIX = "higgsfield/cinema-studio/";
/** Genjutsu de Higgsfield (y su versión Light): motion transfer, object swap y restyle sobre un video de origen. */
const GENJUTSU = /^higgsfield\/genjutsu(-light)?\//;
const genjutsuRank = (id: string) =>
  ["motion-transfer", "object-swap", "restyle"].findIndex((w) => id.includes(`/${w}/`)) * 2 + (id.includes("genjutsu-light/") ? 1 : 0);
const DEFAULTS: Record<Mode, string> = { video: "higgsfield/cinema-studio/4.0", image: "higgsfield-ai/soul/cinema" };
const MAX_BATCH = 4;

const detailCache = new Map<string, Promise<ModelDetail>>();
function loadDetail(id: string) {
  if (!detailCache.has(id)) {
    const p = studio.model(id);
    p.catch(() => detailCache.delete(id));
    detailCache.set(id, p);
  }
  return detailCache.get(id)!;
}

const kindOf = (contentType: string | null | undefined, url = ""): MediaKind =>
  contentType?.startsWith("video/") || /\.(mp4|mov|webm|m4v)(\?|$)/i.test(url)
    ? "video"
    : contentType?.startsWith("audio/") || /\.(mp3|wav|m4a|ogg|aac)(\?|$)/i.test(url)
      ? "audio"
      : "image";

const listOf = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : typeof v === "string" && v ? [v] : []);

/** Seedance 2.5 primero (como en Higgsfield), luego su borrador barato y después el resto. */
const featuredRank = (id: string) => (id.startsWith("bytedance/seedance-2.5/") ? 0 : id.startsWith("bytedance/seedance-2.5-draft/") ? 1 : 2);

/** Modelos del menú del compositor: los de Cinema Studio y algunos destacados que también toman referencias. */
function menuModels(models: ModelSummary[], mode: Mode) {
  if (mode === "video") {
    const cinematic = models.filter((m) => m.id.startsWith(CINEMA_PREFIX) && m.output === "video");
    const featured = models
      .filter((m) => m.output === "video" && !m.id.startsWith(CINEMA_PREFIX) && m.capabilities.includes("reference-to-video"))
      .sort((a, b) => featuredRank(a.id) - featuredRank(b.id) || a.id.localeCompare(b.id))
      .slice(0, 6);
    const genjutsu = models.filter((m) => m.output === "video" && GENJUTSU.test(m.id)).sort((a, b) => genjutsuRank(a.id) - genjutsuRank(b.id));
    return { cinematic, featured, genjutsu };
  }
  const cinematic = models.filter((m) => m.id === DEFAULTS.image);
  const featured = models.filter((m) => m.output === "image" && m.id.startsWith("higgsfield-ai/soul/") && m.id !== DEFAULTS.image).slice(0, 4);
  return { cinematic, featured, genjutsu: [] as ModelSummary[] };
}

export type ComposerHandle = {
  /** Sube archivos y los añade como referencias (botón Upload de la barra del proyecto). */
  addFiles: (files: File[]) => Promise<void>;
};

/**
 * Compositor de Cinema Studio, como el de Higgsfield: Imagen/Video a la izquierda; arriba References y las cuatro
 * tarjetas de dirección; el prompt con @ (elementos) y # (movimientos); abajo el modelo, resolución, formato,
 * duración, audio y lote; y Generar con el precio. Las ventanas se abren ancladas justo encima.
 */
export function Composer({
  ref,
  projectId,
  folderId,
  onGenerated,
  className,
  panelsBelow,
}: {
  ref?: Ref<ComposerHandle>;
  /** Las ventanas se abren debajo (en el inicio, donde arriba no hay sitio). */
  panelsBelow?: boolean;
  /** Proyecto donde se guarda lo generado; sin indicarlo, el proyecto activo. */
  projectId?: string | null;
  folderId?: string | null;
  onGenerated?: (g: Generation) => void;
  className?: string;
}) {
  const { t, locale } = useI18n();
  const c = t.cinemaStudio.composer;
  const [mode, setMode] = useState<Mode>("video");
  const [models, setModels] = useState<ModelSummary[]>([]);
  const [chosen, setChosen] = useState<Record<Mode, string>>(DEFAULTS);
  const modelId = chosen[mode];
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [extra, setExtraState] = useState<CinemaExtra>(EMPTY_CINEMA);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [refsTab, setRefsTab] = useState<RefsTab>("uploads");
  const [cameraTab, setCameraTab] = useState<"setup" | "movement" | undefined>(undefined);
  const [batch, setBatch] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const keys = useRef<string[] | null>(null);
  const batchOf = useRef<string | null>(null); // la petición a la que pertenecen las claves
  const promptRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    studio.models().then((r) => setModels(r.models), (e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  // Esquema del modelo; se conserva lo que siga siendo válido (prompt, referencias compatibles).
  useEffect(() => {
    let alive = true;
    loadDetail(modelId)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        const props = d.input_schema.properties ?? {};
        setValues((prev) => {
          const next = defaultsFor(d.input_schema);
          for (const [k, v] of Object.entries(prev)) {
            const s = props[k];
            if (!s || (s.enum && !s.enum.includes(v as string))) continue;
            next[k] = v;
          }
          return next;
        });
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [modelId]);

  const ready = detail?.id === modelId ? detail : null;
  const fields = useMemo(() => (ready ? fieldsFor(ready.input_schema, ready.id) : []), [ready]);
  const media = fields.filter((f): f is MediaField => f.kind === "media");
  const props = ready?.input_schema.properties ?? {};
  const cinemaKeys = useMemo(() => (ready ? cinemaKeysOf(ready.input_schema) : []), [ready]);
  const isCinema = cinemaKeys.length > 0;
  if (!isCinema && extra !== EMPTY_CINEMA) setExtraState(EMPTY_CINEMA);
  // Lote de 1 a 4: si el modelo admite ese tamaño de lote (`batch_size` de Soul Cinema: 1 o 4) lo hace en una sola
  // generación; si no, se lanzan N generaciones con el lote mínimo del modelo.
  const nativeBatch = (props.batch_size?.enum as number[] | undefined) ?? null;
  const useNative = !!nativeBatch && nativeBatch.includes(batch);
  // Tamaño de lote que va en la petición (null: el modelo no tiene `batch_size`).
  const batchSize = nativeBatch ? (useNative ? batch : Math.min(...nativeBatch)) : null;
  const sendValues = useMemo(() => {
    const cinema = isCinema ? applyCinema(values, extra) : values;
    // @imagen1, @video2… del prompt pasan a la referencia que entiende el modelo (Cinema: <<<image_1>>>).
    const base = typeof cinema.prompt === "string" ? { ...cinema, prompt: resolveRefMentions(cinema.prompt, isCinema) } : cinema;
    return batchSize === null ? base : { ...base, batch_size: batchSize };
  }, [isCinema, values, extra, batchSize]);

  const setValue = useCallback((key: string, v: unknown) => {
    keys.current = null; // otra petición: otras claves
    setValues((prev) => ({ ...prev, [key]: v }));
  }, []);
  const setExtra = useCallback((next: React.SetStateAction<CinemaExtra>) => {
    keys.current = null;
    setExtraState(next);
  }, []);

  // Referencias: todas las casillas de medios del modelo (Cinema Studio: 30 imágenes, 10 videos y 10 audios = 50).
  const refMax = media.reduce((n, f) => n + (f.multiple ? f.max : 1), 0);
  const refs = media.flatMap((f) => listOf(values[f.key]).map((url) => ({ url, kind: f.media, key: f.key })));
  const imageSlot = media.find((f) => f.media === "image" && f.multiple);
  // Genjutsu: casillas propias (video de origen, imágenes) y, en Restyle, el estilo de su catálogo (`preset_id`).
  const isGenjutsu = !!ready && GENJUTSU.test(ready.id);
  const styleField = fields.find((f) => f.kind === "style");
  const [styles, setStyles] = useState<{ model: string; list: ModelStyle[] } | null>(null);
  useEffect(() => {
    if (!styleField || !ready) return;
    let alive = true;
    studio.styles(ready.id).then((r) => alive && setStyles({ model: r.model, list: r.styles }), () => undefined);
    return () => {
      alive = false;
    };
  }, [styleField, ready]);
  const style = styleField && styles?.model === ready?.id ? styles?.list.find((x) => x.id === values[styleField.key]) : undefined;
  const [missing, setMissing] = useState<string[]>([]);
  const slotLabel = (f: MediaField) => (f.media === "video" ? c.sourceVideo : f.media === "image" ? c.refImages : f.label);

  /** Añade una URL a la casilla de su tipo; false si este modelo no la acepta o ya no cabe. */
  // Lo último que se puso en `values`, para añadir varias referencias seguidas (subidas) sin pisarse.
  const latest = useRef(values);
  useEffect(() => {
    latest.current = values;
  }, [values]);
  function addRef(url: string, kind: MediaKind) {
    const slot = media.find((f) => f.media === kind);
    if (!slot) {
      setError(c.notAccepted);
      return false;
    }
    const prev = latest.current;
    const list = listOf(prev[slot.key]);
    if (list.includes(url)) return true;
    if (slot.multiple && list.length >= slot.max) {
      setError(c.full);
      return false;
    }
    const next = { ...prev, [slot.key]: slot.multiple ? [...list, url] : url };
    latest.current = next;
    keys.current = null;
    setValues(next);
    return true;
  }
  // Las menciones <<<image_N>>> (y video/audio) del prompt siguen a su referencia: al quitar una se borra su mención y
  // las siguientes se renumeran; al vaciar las referencias se quitan todas.
  const removeRef = (key: string, url: string) => {
    keys.current = null;
    const kind = media.find((f) => f.key === key)?.media;
    setValues((prev) => {
      const v = prev[key];
      const list = Array.isArray(v) ? (v as string[]) : [];
      const at = list.indexOf(url) + 1;
      const next: Record<string, unknown> = { ...prev, [key]: Array.isArray(v) ? list.filter((u) => u !== url) : undefined };
      if (kind && at > 0 && typeof prev.prompt === "string") next.prompt = renumberRefWords(renumberMentions(prev.prompt, kind, at), kind, at);
      return next;
    });
  };
  const resetRefs = () => {
    keys.current = null;
    setValues((prev) => {
      const next = { ...prev };
      for (const f of media) next[f.key] = undefined;
      if (typeof prev.prompt === "string") next.prompt = stripRefWords(stripMentions(prev.prompt));
      return next;
    });
  };

  async function addFiles(files: File[]) {
    setError(null);
    setUploading(true);
    try {
      for (const f of files) {
        const kind = kindOf(f.type, f.name);
        if (!media.some((m) => m.media === kind)) {
          setError(c.notAccepted);
          continue;
        }
        const up = await studio.upload(f);
        addRef(up.url, kindOf(up.content_type, up.url));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }
  useImperativeHandle(ref, () => ({ addFiles }));

  /** Un elemento: sus imágenes van a la casilla de imágenes y se cita en el prompt (`range`: el @texto a sustituir). */
  async function addElement(el: StudioElement, range?: { start: number; end: number }) {
    if (!imageSlot || !ready) return;
    try {
      const r = await studio.elementUrls(el.id);
      const current = listOf(values[imageSlot.key]);
      const fresh = r.image_urls.filter((u) => !current.includes(u)).slice(0, Math.max(0, imageSlot.max - current.length));
      if (!fresh.length) return setError(c.full);
      setValue(imageSlot.key, [...current, ...fresh]);
      const mention = elementMention(el, ready.id, current.length + 1);
      const text = (values.prompt as string) ?? "";
      const next = range ? `${text.slice(0, range.start)}${mention} ${text.slice(range.end)}` : text ? `${text.trimEnd()} ${mention}` : mention;
      setValue("prompt", next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  // Duración de los videos de referencia (algunos modelos cobran por segundos de entrada).
  const [videoSecs, setVideoSecs] = useState<Record<string, number>>({});
  const videoKey = refs.filter((r) => r.kind === "video").map((r) => r.url).join("|");
  useEffect(() => {
    for (const url of videoKey ? videoKey.split("|") : []) {
      // -1: no se pudo medir (Genjutsu no envía sin saber si cumple su mínimo).
      probeDuration(url).then((secs) => setVideoSecs((prev) => (prev[url] ? prev : { ...prev, [url]: secs || -1 })));
    }
  }, [videoKey]);
  const videoUrls = videoKey ? videoKey.split("|") : [];
  const hints: Record<string, number> = {};
  if (videoUrls.length && videoUrls.every((u) => videoSecs[u] > 0)) hints.input_video_seconds = videoUrls.reduce((n, u) => n + videoSecs[u], 0);
  const hintsKey = JSON.stringify(hints);

  const count = useNative ? 1 : batch;

  // Precio: se recotiza con debounce en cada cambio; el que se ve es N × el de una.
  const estimateKey = ready ? `${ready.id}|${JSON.stringify(cleanInput(sendValues))}|${hintsKey}` : "";
  const [estimated, setEstimated] = useState<{ key: string; value: Estimate | null; error?: string } | null>(null);
  const current = estimated?.key === estimateKey ? estimated : null;
  const [confirmUnknown, setConfirmUnknown] = useState<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    const h = JSON.parse(hintsKey) as Record<string, number>;
    const timer = setTimeout(() => {
      studio
        .estimate(ready.id, cleanInput(sendValues), h)
        .then((r) => setEstimated({ key: estimateKey, value: r }))
        .catch((e) => setEstimated({ key: estimateKey, value: null, error: e instanceof Error ? e.message : String(e) }));
    }, 500);
    return () => clearTimeout(timer);
  }, [ready, sendValues, estimateKey, hintsKey]);
  const unit = current?.value ?? null;
  const total = unit && unit.usd != null ? { ...unit, usd: unit.usd * count } : unit;
  const price = costShort(total);
  const confirming = confirmUnknown === `${estimateKey}|${count}`;

  async function submit() {
    if (!ready || submitting) return;
    const prompt = ((values.prompt as string) ?? "").trim();
    if (props.prompt && ready.input_schema.required?.includes("prompt") && !prompt) {
      promptRef.current?.focus();
      return;
    }
    // Lo obligatorio que falta (video de origen, imágenes, estilo) se marca antes de cotizar nada.
    const required = new Set(ready.input_schema.required ?? []);
    const lacking = [
      ...media.filter((f) => (required.has(f.key) || (f.schema.minItems ?? 0) > 0) && listOf(values[f.key]).length === 0).map((f) => f.key),
      ...(styleField?.required && !values[styleField.key] ? [styleField.key] : []),
    ];
    setMissing(lacking);
    if (lacking.length) {
      const names = lacking.map((k) => (k === styleField?.key ? c.style : slotLabel(media.find((f) => f.key === k)!)));
      setError(c.missing(names.join(", ")));
      if (lacking[0] === styleField?.key) setPanel("style");
      return;
    }
    const source = isGenjutsu && !ready.id.includes("genjutsu-light/") ? listOf(values.video_url)[0] : undefined;
    if (source) {
      const secs = videoSecs[source];
      if (secs === undefined) return setError(c.videoMeasuring);
      if (secs < 0) return setError(c.videoUnmeasurable);
      if (secs < 4) return setError(c.videoTooShort);
    }
    if (!costAllowsDirectSubmit(unit) && !confirming) {
      setConfirmUnknown(`${estimateKey}|${count}`);
      return;
    }
    setConfirmUnknown(null);
    setSubmitting(true);
    setError(null);
    setNotice(null);
    const input = cleanInput(sendValues);
    const place = projectId === undefined ? activeProject() : projectId;
    // Una clave por posición del lote, atada a la petición exacta (modelo, entrada, lote, proyecto y carpeta): reintentar
    // la misma tras un fallo parcial recupera las ya aceptadas (el servidor deduplica por clave) y solo crea las que
    // faltan; cualquier cambio de la petición, por cualquier vía (modo, esquema, controles), estrena claves.
    const identity = JSON.stringify([ready.id, input, count, place ?? null, folderId ?? null, hintsKey]);
    if (!keys.current || batchOf.current !== identity) {
      keys.current = Array.from({ length: count }, () => crypto.randomUUID());
      batchOf.current = identity;
    }
    let launched = 0;
    try {
      for (const key of keys.current) {
        const g = await studio.generate(
          ready.id,
          input,
          key,
          false,
          unit?.usd ?? null,
          JSON.parse(hintsKey) as Record<string, number>,
          unit?.reserve_usd ?? null,
          // Llegar aquí sin precio completo significa que el usuario confirmó un costo desconocido.
          !costAllowsDirectSubmit(unit),
          count > 1,
          place,
          folderId ?? null,
        );
        launched += 1;
        onGenerated?.(g);
      }
      keys.current = null;
      setNotice(c.launched(launched));
    } catch (e) {
      const bad = fieldErrors(e);
      if (e instanceof StudioError && e.code === "cost_changed") {
        const fresh = await studio.estimate(ready.id, input, JSON.parse(hintsKey)).catch(() => null);
        setEstimated({ key: estimateKey, value: fresh });
        setError(fresh?.usd != null ? t.cost.priceChanged(formatUsd(fresh.usd)) : e.message);
      } else if (bad) {
        setError(bad.map((d) => `${d.path}: ${d.message}`).join(" · "));
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
      if (launched > 0 && launched < count) setNotice(c.partial(launched, count));
    } finally {
      setSubmitting(false);
    }
  }

  // @ en el prompt: menú de elementos (si el modelo toma imágenes de referencia).
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const loadElements = useCallback(() => {
    if (elements === null) studio.elements().then((r) => setElements(r.elements), () => setElements([]));
  }, [elements]);
  const [at, setAt] = useState<{ query: string; start: number; end: number } | null>(null);
  const [atIndex, setAtIndex] = useState(0);
  // Menú de @: primero las referencias adjuntas en su orden (@imagen1, @video1…), después los elementos.
  const refKey = refs.map((r) => `${r.kind}|${r.key}|${r.url}`).join("\n");
  const refOptions = useMemo(() => {
    const seen: Record<string, number> = {};
    return refKey
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [kind, key, url] = line.split("|") as [MediaKind, string, string];
        seen[kind] = (seen[kind] ?? 0) + 1;
        const word = kind === "image" ? (locale === "es" ? "imagen" : "image") : kind;
        return { kind, key, url, name: `${word}${seen[kind]}` };
      });
  }, [refKey, locale]);
  const q = at?.query.toLowerCase() ?? "";
  const refMatches = at ? refOptions.filter((r) => r.name.includes(q)) : [];
  const atMatches = at ? (elements ?? []).filter((el) => el.name.includes(q)).slice(0, 6) : [];
  const atTotal = refMatches.length + atMatches.length;
  function pickAt(i: number) {
    if (!at) return;
    if (i < refMatches.length) {
      const text = (values.prompt as string) ?? "";
      setValue("prompt", `${text.slice(0, at.start)}@${refMatches[i].name} ${text.slice(at.end)}`);
    } else {
      const el = atMatches[i - refMatches.length];
      if (el) void addElement(el, at);
    }
    setAt(null);
  }
  function checkAt(el: HTMLTextAreaElement) {
    if (!imageSlot && !refs.length) return setAt(null);
    const caret = el.selectionStart ?? 0;
    const m = /(^|\s)@(\w*)$/.exec(el.value.slice(0, caret));
    if (!m) return setAt(null);
    loadElements();
    setAt((prev) => {
      if (!prev || prev.query !== m[2]) setAtIndex(0);
      return { query: m[2], start: caret - m[2].length - 1, end: caret };
    });
  }

  const lackingNow = missing.filter((k) => (k === styleField?.key ? !values[k] : listOf(values[k]).length === 0));

  const openPanel = (p: Panel | null, opts?: { tab?: RefsTab; cameraTab?: "setup" | "movement" }) => {
    if (opts?.tab) setRefsTab(opts.tab);
    setCameraTab(opts?.cameraTab);
    setPanel((cur) => (cur === p && !opts ? null : p));
  };

  const { cinematic, featured, genjutsu } = menuModels(models, mode);
  const label = ready ? modelLabel(ready.title) : null;
  // Genjutsu: el nombre solo no distingue sus tres funciones («Genjutsu · Restyle»).
  const modelTitle = label ? (isGenjutsu ? `${label.name} · ${label.workflow}` : label.name) : (models.find((m) => m.id === modelId)?.title.split(" — ")[0] ?? "…");
  const resolution = props.resolution?.enum as string[] | undefined;
  const ratios = props.aspect_ratio?.enum as string[] | undefined;
  const duration = props.duration;
  const hasAudio = props.generate_audio?.type === "boolean";

  const refsCard = refMax > 0 && (
    <button
      type="button"
      onClick={() => openPanel("refs")}
      className={clsx(
        "flex h-12 min-w-[118px] shrink-0 items-center gap-2.5 rounded-xl border py-1.5 pr-3 pl-1.5 text-left transition-colors hover:bg-surface-4",
        panel === "refs" ? "border-line-2 bg-surface-4" : "border-transparent bg-surface-3",
      )}
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-5 text-fg-2">
        <Plus className="size-4" />
      </span>
      <span className="min-w-0">
        <span className="block truncate font-mono text-[10px] leading-tight text-fg-3">{c.references}</span>
        <span className="block text-[14px] leading-tight font-semibold text-fg">
          {refs.length}/{refMax}
        </span>
      </span>
    </button>
  );

  return (
    <div className={clsx("flex w-full flex-col gap-2 sm:flex-row sm:items-end", className)}>
      {/* Imagen / Video */}
      <div className="flex shrink-0 gap-1 rounded-2xl border border-line bg-surface-2 p-1 sm:flex-col">
        {(["image", "video"] as const).map((m) => {
          const Icon = m === "image" ? ImageIcon : Video;
          return (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setPanel(null);
              }}
              className={clsx(
                "flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-[11px] font-semibold transition-colors sm:flex-col sm:gap-1 sm:px-2.5 sm:py-2.5",
                mode === m ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg-2",
              )}
            >
              <Icon className="size-4" />
              {m === "image" ? c.image : c.video}
            </button>
          );
        })}
      </div>

      {/* Caja del compositor: ancla de las ventanas */}
      <div className="relative min-w-0 flex-1 rounded-[22px] border border-line-2 bg-surface-2 p-1.5 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)]">
        <CinemaAnchorContext.Provider value={panelsBelow ? "below" : "above"}>
          {isCinema ? (
            <CinemaControls
              variant="row"
              keys={cinemaKeys}
              values={values}
              setValue={setValue}
              extra={extra}
              setExtra={setExtra}
              lead={refsCard}
              names={{ film: c.filmSetup, camera: c.camera, palette: c.palette, light: c.lighting }}
              open={panel === "refs" || panel === "style" ? null : panel}
              onOpenChange={(p) => openPanel(p)}
              cameraTab={cameraTab}
            />
          ) : isGenjutsu ? (
            <div className="hide-scrollbar flex gap-1.5 overflow-x-auto">
              {media.map((f) => {
                const list = listOf(values[f.key]);
                return (
                  <SlotCard
                    key={f.key}
                    active={panel === "refs"}
                    warn={lackingNow.includes(f.key)}
                    onClick={() => openPanel("refs", { tab: "uploads" })}
                    thumb={list[0] ? <RefThumb url={list[0]} kind={f.media} className="size-full" /> : <Plus className="size-4" />}
                    caption={slotLabel(f)}
                    value={f.multiple ? `${list.length}/${f.max}` : list.length ? "1/1" : "0/1"}
                  />
                );
              })}
              {styleField && (
                <SlotCard
                  active={panel === "style"}
                  warn={lackingNow.includes(styleField.key)}
                  onClick={() => openPanel("style")}
                  thumb={
                    style?.preview_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={style.preview_url} alt="" className="size-full object-cover" />
                    ) : (
                      <Palette className="size-4" />
                    )
                  }
                  caption={c.style}
                  value={style?.name ?? (values[styleField.key] ? String(values[styleField.key]).slice(0, 8) : c.pickStyle)}
                />
              )}
            </div>
          ) : (
            refsCard && <div className="flex">{refsCard}</div>
          )}
        </CinemaAnchorContext.Provider>

        {panel === "style" && styleField && ready && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setPanel(null)} />
            <div className={clsx("absolute inset-x-0 z-50 overflow-hidden rounded-panel shadow-2xl", panelsBelow ? "top-full mt-2" : "bottom-full mb-2")}>
              <StylePicker
                key={`${ready.id}/style`}
                model={ready.id}
                value={values[styleField.key] as string | undefined}
                onChange={(v) => {
                  setValue(styleField.key, v);
                  if (v) setPanel(null);
                }}
                error={lackingNow.includes(styleField.key) ? t.styles.required : undefined}
              />
            </div>
          </>
        )}

        {panel === "refs" && (
          <ReferencesPanel
            tab={refsTab}
            setTab={setRefsTab}
            kinds={(["image", "video", "audio"] as const).filter((k) => media.some((f) => f.media === k))}
            refs={refs}
            canElements={!!imageSlot}
            uploading={uploading}
            onUpload={addFiles}
            onAdd={addRef}
            onRemove={removeRef}
            onElement={(el) => void addElement(el)}
            onReset={resetRefs}
            below={panelsBelow}
            onClose={() => setPanel(null)}
          />
        )}

        <div className="mt-1.5 flex flex-col gap-1.5 sm:flex-row">
          <div className="relative min-w-0 flex-1 rounded-2xl bg-surface-3 px-2.5 pt-2 pb-2">
            {refs.length > 0 && (
              <div className="hide-scrollbar mb-1.5 flex gap-1.5 overflow-x-auto">
                {refs.map((r) => (
                  <span key={`${r.key}|${r.url}`} className="relative shrink-0">
                    <RefThumb url={r.url} kind={r.kind} className="size-11" />
                    <button
                      type="button"
                      aria-label={c.removeRef}
                      onClick={() => removeRef(r.key, r.url)}
                      className="absolute -top-1 -right-1 rounded-full bg-surface-1 p-0.5 text-fg-2 ring-1 ring-line hover:text-fg"
                    >
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <textarea
              ref={promptRef}
              value={(values.prompt as string) ?? ""}
              onChange={(e) => {
                setValue("prompt", e.target.value || undefined);
                checkAt(e.target);
              }}
              onClick={(e) => checkAt(e.currentTarget)}
              onBlur={() => setTimeout(() => setAt(null), 150)}
              onPaste={(e) => {
                const files = Array.from(e.clipboardData.files);
                if (files.length) {
                  e.preventDefault();
                  void addFiles(files);
                }
              }}
              onKeyDown={(e) => {
                if (at && atTotal) {
                  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                    e.preventDefault();
                    setAtIndex((i) => (i + (e.key === "ArrowDown" ? 1 : -1) + atTotal) % atTotal);
                    return;
                  }
                  if (e.key === "Enter" || e.key === "Tab") {
                    e.preventDefault();
                    pickAt(Math.min(atIndex, atTotal - 1));
                    return;
                  }
                }
                if (e.key === "Escape") setAt(null);
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit();
              }}
              rows={2}
              placeholder={isGenjutsu ? c.placeholderGenjutsu : mode === "video" ? c.placeholderVideo : c.placeholderImage}
              className="thin-scrollbar max-h-40 min-h-12 w-full resize-none bg-transparent px-1 text-[15px] leading-relaxed text-fg outline-none placeholder:text-fg-4"
            />
            {at && (
              <div className="absolute inset-x-2 bottom-full z-30 mb-1 overflow-hidden rounded-2xl border border-line-2 bg-surface-2 p-1 shadow-2xl">
                {refMatches.map((r, i) => (
                  <button
                    key={`${r.key}:${r.url}`}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setAtIndex(i)}
                    onClick={() => pickAt(i)}
                    className={clsx("flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left", i === atIndex && "bg-surface-4")}
                  >
                    <RefThumb url={r.url} kind={r.kind} className="size-7 rounded-md" />
                    <span className="font-mono text-[13px] font-semibold">@{r.name}</span>
                    <span className="min-w-0 flex-1 truncate text-xs text-fg-3">{c.refHint}</span>
                  </button>
                ))}
                {elements === null ? (
                  <Loader2 className="m-2 size-4 animate-spin text-fg-3" />
                ) : atMatches.length === 0 ? (
                  refMatches.length === 0 && <p className="px-2.5 py-1.5 text-[13px] text-fg-3">{c.noElements}</p>
                ) : (
                  atMatches.map((el, j) => (
                    <button
                      key={el.id}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onMouseEnter={() => setAtIndex(refMatches.length + j)}
                      onClick={() => pickAt(refMatches.length + j)}
                      className={clsx("flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left", refMatches.length + j === atIndex && "bg-surface-4")}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={apiSrc(el.images[0])} alt="" className="size-7 rounded-md object-cover" />
                      <span className="font-mono text-[13px] font-semibold">{el.mention}</span>
                      <span className="min-w-0 flex-1 truncate text-xs text-fg-3">{el.description}</span>
                    </button>
                  ))
                )}
              </div>
            )}
            {cinemaKeys.includes("camera_movement") && (
              <HashMovementMenu above textareaRef={promptRef} keys={cinemaKeys} values={values} setValue={setValue} extra={extra} setExtra={setExtra} />
            )}

            <div className="mt-1 flex flex-wrap items-center gap-0.5">
              {refMax > 0 && (
                <IconChip title={c.addReferences} onClick={() => openPanel("refs", { tab: "uploads" })}>
                  <Plus className="size-4" />
                </IconChip>
              )}
              {imageSlot && (
                <IconChip title={c.mention} onClick={() => openPanel("refs", { tab: "elements" })}>
                  <AtSign className="size-4" />
                </IconChip>
              )}
              {cinemaKeys.includes("camera_movement") && (
                <IconChip title={c.movement} onClick={() => openPanel("camera", { cameraTab: "movement" })}>
                  <ScanEye className="size-4" />
                </IconChip>
              )}
              <Pop
                className="w-[min(340px,calc(100vw-2rem))]"
                trigger={
                  <>
                    <Sparkles className="size-3.5 text-lime" />
                    <span className="max-w-40 truncate">{modelTitle}</span>
                    <ChevronRight className="size-3.5 text-fg-3" />
                  </>
                }
              >
                {(close) => (
                  <ModelMenu
                    groups={
                      mode === "video"
                        ? [
                            [c.cinematicModels, cinematic],
                            [c.featuredModels, featured],
                            [c.genjutsuModels, genjutsu],
                          ]
                        : [
                            [c.imageModels, cinematic],
                            [c.featuredModels, featured],
                          ]
                    }
                    selected={modelId}
                    onPick={(id) => {
                      keys.current = null;
                      setMissing([]);
                      setError(null);
                      setChosen((prev) => ({ ...prev, [mode]: id }));
                      close();
                    }}
                  />
                )}
              </Pop>
              {resolution && (
                <Pop trigger={<><Gem className="size-3.5" />{String(values.resolution ?? resolution[0])}</>}>
                  {(close) => (
                    <OptionList
                      title={c.resolution}
                      options={resolution}
                      value={values.resolution}
                      onPick={(v) => {
                        setValue("resolution", v);
                        close();
                      }}
                      note={isCinema ? c.resolutionNote : undefined}
                    />
                  )}
                </Pop>
              )}
              {ratios && (
                <Pop trigger={<><RatioIcon value={String(values.aspect_ratio ?? ratios[0])} />{String(values.aspect_ratio ?? ratios[0])}</>}>
                  {(close) => (
                    <OptionList
                      title={c.ratio}
                      options={ratios}
                      icon={(v) => <RatioIcon value={v} />}
                      value={values.aspect_ratio}
                      onPick={(v) => {
                        setValue("aspect_ratio", v);
                        close();
                      }}
                    />
                  )}
                </Pop>
              )}
              {duration && (duration.enum || duration.maximum != null) && (
                <Pop trigger={<><Clock className="size-3.5" />{`${values.duration ?? duration.default ?? ""}s`}</>}>
                  {(close) =>
                    duration.enum ? (
                      <OptionList
                        title={c.duration}
                        options={duration.enum.map(String)}
                        value={String(values.duration)}
                        format={(v) => `${v}s`}
                        onPick={(v) => {
                          setValue("duration", Number(v));
                          close();
                        }}
                      />
                    ) : (
                      <div className="w-60 p-2">
                        <p className="mb-2 flex justify-between text-xs font-semibold text-fg-3">
                          {c.duration}
                          <span className="font-mono text-fg">{`${values.duration ?? duration.default}s`}</span>
                        </p>
                        <input
                          type="range"
                          min={duration.minimum ?? 1}
                          max={duration.maximum}
                          value={Number(values.duration ?? duration.default ?? duration.minimum ?? 1)}
                          onChange={(e) => setValue("duration", Number(e.target.value))}
                          className="w-full"
                          aria-label={c.duration}
                        />
                        <p className="mt-1 flex justify-between font-mono text-[11px] text-fg-4">
                          <span>{duration.minimum ?? 1}s</span>
                          <span>{duration.maximum}s</span>
                        </p>
                      </div>
                    )
                  }
                </Pop>
              )}
              {hasAudio && (
                <button type="button" onClick={() => setValue("generate_audio", !(values.generate_audio ?? true))} className={CHIP} title={c.audio}>
                  {values.generate_audio === false ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
                  {values.generate_audio === false ? c.off : c.on}
                </button>
              )}
              <BatchStepper
                value={batch}
                options={[1, 2, 3, 4]}
                title={c.batchHint(batch)}
                onChange={(n) => {
                  keys.current = null;
                  setBatch(n);
                }}
              />
            </div>
          </div>

          <button
            type="button"
            onClick={() => void submit()}
            disabled={!ready || submitting}
            className="flex min-h-14 shrink-0 flex-col items-center justify-center gap-0.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime px-6 text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] transition-[filter,transform] hover:brightness-105 active:translate-y-px disabled:opacity-50 sm:w-32"
          >
            {submitting ? (
              <Loader2 className="size-5 animate-spin" />
            ) : (
              <>
                <span className="text-[13px] font-bold tracking-wide uppercase">{confirming ? t.studio.generateAnyway : c.generate}</span>
                <span className="flex items-center gap-1 text-[13px] font-semibold">
                  {!current ? <Loader2 className="size-3 animate-spin" /> : <>{price ?? c.priceUnknown}</>}
                </span>
              </>
            )}
          </button>
        </div>
        {(error || notice || confirming || current?.error) && (
          <p className={clsx("px-2 pt-1.5 text-xs", error || current?.error ? "text-danger" : confirming ? "text-warning" : "text-fg-3")}>
            {error ?? current?.error ?? (confirming ? c.confirmUnknown : notice)}
          </p>
        )}
      </div>
    </div>
  );
}

const CHIP = "flex h-8 items-center gap-1 rounded-lg bg-surface-4/60 px-2 text-[13px] font-semibold text-fg-2 transition-colors hover:bg-surface-5 hover:text-fg";

function IconChip({ title, onClick, children }: { title: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" title={title} aria-label={title} onClick={onClick} className="flex size-8 items-center justify-center rounded-lg text-fg-2 transition-colors hover:bg-surface-5 hover:text-fg">
      {children}
    </button>
  );
}

/** Chip con un menú pequeño que se abre encima; clic fuera o Escape lo cierran. */
function Pop({ trigger, children, className }: { trigger: ReactNode; children: (close: () => void) => ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  // El menú sale del chip hacia la derecha; si no cabe en la pantalla (móvil), se desplaza hasta que quepa.
  useLayoutEffect(() => {
    const el = panel.current;
    if (!open || !el) return;
    el.style.transform = "";
    const r = el.getBoundingClientRect();
    const margin = 8;
    const shift = r.right > window.innerWidth - margin ? window.innerWidth - margin - r.right : r.left < margin ? margin - r.left : 0;
    if (shift) el.style.transform = `translateX(${shift}px)`;
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className={clsx(CHIP, open && "bg-surface-5 text-fg")}>
        {trigger}
      </button>
      {open && (
        <div ref={panel} className={clsx("absolute bottom-full left-0 z-40 mb-2 rounded-xl border border-line-2 bg-surface-2 p-1 shadow-2xl", className)}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

function OptionList({
  title,
  options,
  value,
  onPick,
  note,
  format = (v) => v,
  icon,
}: {
  title: string;
  options: string[];
  value: unknown;
  onPick: (v: string) => void;
  note?: string;
  format?: (v: string) => string;
  icon?: (v: string) => ReactNode;
}) {
  return (
    <div className="w-44">
      <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold text-fg-4">{title}</p>
      {options.map((o) => (
        <button key={o} type="button" onClick={() => onPick(o)} className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[13px] font-semibold hover:bg-surface-4">
          <span className="flex items-center gap-2">
            {icon?.(o)}
            {format(o)}
          </span>
          {String(value) === o && <Check className="size-4 text-lime" />}
        </button>
      ))}
      {note && <p className="px-2.5 pt-1 pb-1.5 text-[11px] text-fg-3">{note}</p>}
    </div>
  );
}

function BatchStepper({ value, options, title, onChange }: { value: number; options: number[]; title: string; onChange: (n: number) => void }) {
  const i = Math.max(0, options.indexOf(value));
  const max = options[options.length - 1] ?? MAX_BATCH;
  return (
    <div title={title} className="flex h-8 items-center rounded-lg bg-surface-4/60 text-[13px] font-semibold">
      <button type="button" aria-label="-" disabled={i === 0} onClick={() => onChange(options[i - 1])} className="px-2 text-fg-3 hover:text-fg disabled:opacity-30">
        <Minus className="size-3.5" />
      </button>
      <span className="font-mono">
        <span className="text-fg">{value}</span>
        <span className="text-fg-4">/{max}</span>
      </span>
      <button type="button" aria-label="+" disabled={i >= options.length - 1} onClick={() => onChange(options[i + 1])} className="px-2 text-fg-3 hover:text-fg disabled:opacity-30">
        <Plus className="size-3.5" />
      </button>
    </div>
  );
}

function ModelMenu({
  groups,
  selected,
  onPick,
}: {
  groups: [string, ModelSummary[]][];
  selected: string;
  onPick: (id: string) => void;
}) {
  const { t } = useI18n();
  const c = t.cinemaStudio.composer;
  const [q, setQ] = useState("");
  const match = (m: ModelSummary) => !q || m.title.toLowerCase().includes(q.toLowerCase()) || m.id.includes(q.toLowerCase());
  const lists = groups.map(([title, list]) => [title, list.filter(match)] as const);
  return (
    <div className="max-h-[min(60vh,460px)] overflow-y-auto">
      <label className="flex items-center gap-2 border-b border-line px-2.5 py-2">
        <Search className="size-4 text-fg-3" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={c.search} className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-fg-4" />
      </label>
      {lists.every(([, l]) => l.length === 0) && <p className="px-3 py-3 text-sm text-fg-3">{c.noModels}</p>}
      {lists.map(([title, list]) =>
        list.length === 0 ? null : (
          <div key={title} className="py-1">
            <p className="flex items-center gap-1.5 px-2.5 pt-1.5 pb-1 text-[12px] font-medium text-fg-3">
              <Sparkles className="size-3" /> {title}
            </p>
            {list.map((m) => {
              const { name, workflow } = modelLabel(m.title);
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => onPick(m.id)}
                  className={clsx("flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left", m.id === selected ? "bg-surface-4" : "hover:bg-surface-3")}
                >
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-5 text-fg-2">
                    {m.output === "video" ? <Film className="size-4" /> : <ImageIcon className="size-4" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-fg">{name}</span>
                    <span className="block truncate text-[11.5px] text-fg-3">{workflow}{m.store ? " · APIMart / KIE" : ""}</span>
                  </span>
                  {m.id === selected && <Check className="size-4 text-lime" />}
                </button>
              );
            })}
          </div>
        ),
      )}
    </div>
  );
}

/** Tarjeta de la fila de arriba (Genjutsu): una casilla de entrada o el estilo, con su miniatura y su estado. */
function SlotCard({ active, warn, onClick, thumb, caption, value }: { active: boolean; warn: boolean; onClick: () => void; thumb: ReactNode; caption: string; value: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex h-12 min-w-[118px] shrink-0 items-center gap-2.5 rounded-xl border py-1.5 pr-3 pl-1.5 text-left transition-colors hover:bg-surface-4",
        warn ? "border-danger/60 bg-surface-3" : active ? "border-line-2 bg-surface-4" : "border-transparent bg-surface-3",
      )}
    >
      <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-5 text-fg-2">{thumb}</span>
      <span className="min-w-0">
        <span className={clsx("block truncate font-mono text-[10px] leading-tight", warn ? "text-danger" : "text-fg-3")}>{caption}</span>
        <span className="block max-w-32 truncate text-[14px] leading-tight font-semibold text-fg">{value}</span>
      </span>
    </button>
  );
}

function RefThumb({ url, kind, className }: { url: string; kind: MediaKind; className?: string }) {
  return (
    <span className={clsx("relative flex items-center justify-center overflow-hidden rounded-lg bg-surface-5", className)}>
      {kind === "video" ? (
        <video src={url} muted playsInline preload="metadata" className="size-full object-cover" />
      ) : kind === "audio" ? (
        <Music className="size-4 text-fg-2" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" />
      )}
      {kind === "video" && <Film className="absolute right-0.5 bottom-0.5 size-3 text-white drop-shadow" />}
    </span>
  );
}

type Item = { id: string; url: string; kind: MediaKind; source?: string; label: string };

/**
 * Panel de References, anclado encima del compositor: subidas, elementos, generaciones y favoritas. Las generaciones
 * se añaden con su URL vigente (gratis) y las subidas con la suya.
 */
function ReferencesPanel({
  tab,
  setTab,
  kinds,
  refs,
  canElements,
  uploading,
  onUpload,
  onAdd,
  onRemove,
  onElement,
  onReset,
  onClose,
  below,
}: {
  below?: boolean;
  tab: RefsTab;
  setTab: (t: RefsTab) => void;
  kinds: MediaKind[];
  refs: { url: string; kind: MediaKind; key: string }[];
  canElements: boolean;
  uploading: boolean;
  onUpload: (files: File[]) => Promise<void>;
  onAdd: (url: string, kind: MediaKind) => boolean;
  onRemove: (key: string, url: string) => void;
  onElement: (el: StudioElement) => void;
  onReset: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const c = t.cinemaStudio.composer;
  const [kind, setKind] = useState<MediaKind | "all">("all");
  const [items, setItems] = useState<Record<string, Item[] | null>>({});
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const [category, setCategory] = useState<ElementCategory | "all">("all");
  const [busy, setBusy] = useState<string | null>(null);
  // Generación elegida → URL vigente que se añadió (para poder quitarla con otro clic).
  const [added, setAdded] = useState<Record<string, string>>({});
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  useEffect(() => {
    if (tab === "elements") {
      if (elements === null) studio.elements().then((r) => setElements(r.elements), () => setElements([]));
      return;
    }
    if (items[tab] !== undefined) return;
    const fromGens = (gs: Generation[]): Item[] =>
      gs
        .filter((g) => g.status === "completed" && g.outputs[0] && ["image", "video", "audio"].includes(g.outputs[0].kind))
        .map((g) => {
          const prompt = typeof g.input.prompt === "string" ? g.input.prompt.slice(0, 80) : "";
          return { id: g.id, url: outputSrc(g.outputs[0]), kind: g.outputs[0].kind as MediaKind, source: g.id, label: `${g.outputs[0].kind}: ${prompt || g.model}` };
        });
    const load: Promise<Item[]> =
      tab === "uploads"
        ? studio.uploads(60).then((r) => r.uploads.map((u) => ({ id: u.id, url: u.url, kind: kindOf(u.content_type, u.url), label: u.filename || u.url })))
        : studio.list(100, false, tab === "liked").then((r) => fromGens(r.generations));
    load.then(
      (list) => setItems((prev) => ({ ...prev, [tab]: list })),
      () => setItems((prev) => ({ ...prev, [tab]: [] })),
    );
  }, [tab, items, elements]);

  const chosen = new Set(refs.map((r) => r.url));
  const list = (items[tab] ?? null)?.filter((it) => kinds.includes(it.kind) && (kind === "all" || it.kind === kind)) ?? null;

  async function toggle(it: Item) {
    const url = it.source ? added[it.source] : it.url;
    const ref = url ? refs.find((r) => r.url === url) : undefined;
    if (ref) return onRemove(ref.key, ref.url);
    if (!it.source) return void onAdd(it.url, it.kind);
    setBusy(it.id);
    try {
      const r = await studio.useOutput(it.source, 0);
      if (onAdd(r.url, it.kind)) setAdded((prev) => ({ ...prev, [it.source!]: r.url }));
    } catch {
      /* salida que ya no existe: se ignora */
    } finally {
      setBusy(null);
    }
  }

  const tabs: RefsTab[] = canElements ? ["uploads", "elements", "generations", "liked"] : ["uploads", "generations", "liked"];
  const accept = kinds.map((k) => `${k}/*`).join(",");

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className={clsx("absolute inset-x-0 z-50 flex max-h-[min(66dvh,560px)] flex-col overflow-hidden rounded-panel border border-line bg-surface-2 shadow-2xl", below ? "top-full mt-2" : "bottom-full mb-2")}>
        <div className="flex items-center gap-1 border-b border-line p-2">
          <div className="hide-scrollbar flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {tabs.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setTab(k)}
                className={clsx("h-8 shrink-0 rounded-full px-3.5 text-[13px] font-semibold", tab === k ? "bg-fg text-ink" : "text-fg-3 hover:text-fg")}
              >
                {c.tabs[k]}
              </button>
            ))}
          </div>
          {refs.length > 0 && (
            <button type="button" onClick={onReset} className="h-8 shrink-0 rounded-full bg-surface-4 px-3 text-[13px] font-semibold text-fg-2 hover:text-fg">
              {c.resetAll}
            </button>
          )}
          <button type="button" onClick={onClose} aria-label={c.close} className="rounded-full p-1.5 text-fg-3 hover:bg-glass hover:text-fg">
            <X className="size-5" />
          </button>
        </div>

        {tab === "elements" ? (
          <div className="flex min-h-0 flex-1 flex-col sm:flex-row">
            <nav className="hide-scrollbar flex shrink-0 gap-1 overflow-x-auto border-b border-line p-2 sm:w-40 sm:flex-col sm:border-r sm:border-b-0">
              {(["all", ...CATEGORIES] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setCategory(k)}
                  className={clsx("shrink-0 rounded-lg px-3 py-1.5 text-left text-[13px] font-semibold", category === k ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg")}
                >
                  {k === "all" ? c.elementsAll : t.elements.categories[k]}
                </button>
              ))}
            </nav>
            <div className="thin-scrollbar grid min-h-0 flex-1 auto-rows-min grid-cols-3 gap-2 overflow-y-auto p-3 sm:grid-cols-4 lg:grid-cols-5">
              <Link
                href="/elements"
                className="flex aspect-square flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line-2 text-[12px] font-semibold text-fg-2 hover:border-lime/50 hover:text-fg"
              >
                <Plus className="size-5" /> {c.newElement}
              </Link>
              {elements === null
                ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="shimmer aspect-square rounded-xl" />)
                : elements
                    .filter((el) => category === "all" || (el.category ?? "other") === category)
                    .map((el) => (
                      <button
                        key={el.id}
                        type="button"
                        title={el.description}
                        onClick={() => {
                          onElement(el);
                          onClose();
                        }}
                        className="group relative aspect-square overflow-hidden rounded-xl bg-surface-3"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={apiSrc(el.images[0])} alt="" className="size-full object-cover transition group-hover:scale-105" />
                        <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-2 pt-4 pb-1.5 text-left font-mono text-[12px] font-semibold text-white">
                          {el.mention}
                        </span>
                      </button>
                    ))}
              {elements?.length === 0 && <p className="col-span-full text-sm text-fg-3">{c.noElements}</p>}
            </div>
          </div>
        ) : (
          <>
            <div className="flex gap-1 border-b border-line px-2 py-1.5">
              {(["all", ...kinds] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setKind(k)}
                  className={clsx("h-7 rounded-lg px-3 text-[12.5px] font-semibold", kind === k ? "bg-surface-5 text-fg" : "text-fg-3 hover:text-fg")}
                >
                  {k === "all" ? c.all : k === "image" ? t.cinemaStudio.images : k === "video" ? t.cinemaStudio.videos : c.audioKind}
                </button>
              ))}
            </div>
            <div className="thin-scrollbar grid min-h-0 flex-1 auto-rows-min grid-cols-3 gap-2 overflow-y-auto p-3 sm:grid-cols-4 lg:grid-cols-5">
              {tab === "uploads" && (
                <>
                  <input
                    ref={file}
                    type="file"
                    multiple
                    hidden
                    accept={accept}
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? []);
                      e.target.value = "";
                      // Al terminar, la lista de subidas se vuelve a leer con las nuevas.
                      void onUpload(files).then(() =>
                        setItems((prev) => {
                          const next = { ...prev };
                          delete next.uploads;
                          return next;
                        }),
                      );
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => file.current?.click()}
                    disabled={uploading}
                    className="flex aspect-square flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-line-2 bg-surface-3 text-[12px] font-semibold text-fg-2 hover:border-lime/50 hover:text-fg"
                  >
                    {uploading ? <Loader2 className="size-5 animate-spin" /> : <Plus className="size-5" />}
                    {c.uploadMedia}
                  </button>
                </>
              )}
              {list === null
                ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="shimmer aspect-square rounded-xl" />)
                : list.map((it) => {
                    const on = it.source ? !!added[it.source] && chosen.has(added[it.source]) : chosen.has(it.url);
                    return (
                      <button
                        key={it.id}
                        type="button"
                        disabled={busy !== null}
                        aria-label={it.label}
                        aria-pressed={on}
                        title={it.label}
                        onClick={() => void toggle(it)}
                        className={clsx("relative aspect-square overflow-hidden rounded-xl bg-surface-3 ring-lime transition hover:ring-2", on && "ring-2")}
                      >
                        <RefThumb url={it.url} kind={it.kind} className="size-full rounded-none" />
                        {on && (
                          <span className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-full bg-lime text-ink">
                            <Check className="size-3.5" />
                          </span>
                        )}
                        {busy === it.id && (
                          <span className="absolute inset-0 flex items-center justify-center bg-black/50">
                            <Loader2 className="size-5 animate-spin text-lime" />
                          </span>
                        )}
                      </button>
                    );
                  })}
              {list?.length === 0 && tab !== "uploads" && <p className="col-span-full text-sm text-fg-3">{c.nothingHere}</p>}
            </div>
          </>
        )}
      </div>
    </>
  );
}

const MENTION = /\s?<<<(image|video|audio)_(\d+)>>>/g;

/** Quita la mención de la referencia `removed` (1, 2…) de ese tipo y baja un número las siguientes. */
export function renumberMentions(prompt: string, kind: string, removed: number): string {
  return prompt.replace(MENTION, (whole, k: string, n: string) => {
    if (k !== kind) return whole;
    const i = Number(n);
    if (i === removed) return "";
    return i > removed ? whole.replace(`_${i}>>>`, `_${i - 1}>>>`) : whole;
  });
}

/** Quita todas las menciones de referencias. */
export function stripMentions(prompt: string): string {
  return prompt.replace(MENTION, "");
}

const kindOfWord = (w: string) => (w.toLowerCase().startsWith("imag") ? "image" : w.toLowerCase());

/** Cambia @imagen1, @image2, @video1, @audio1… por la referencia del modelo: en Cinema Studio <<<image_1>>>; en otros
 * modelos un texto claro («reference image 1»). */
export function resolveRefMentions(prompt: string, cinema: boolean): string {
  return prompt.replace(/@(imagen|image|video|audio)(\d+)\b/gi, (_w, word: string, n: string) => {
    const kind = kindOfWord(word);
    return cinema ? `<<<${kind}_${n}>>>` : `reference ${kind} ${n}`;
  });
}

/** Al quitar la referencia `removed` de un tipo: su @mención se borra y las siguientes bajan un número. */
export function renumberRefWords(prompt: string, kind: string, removed: number): string {
  return prompt.replace(/\s?@(imagen|image|video|audio)(\d+)\b/gi, (whole, word: string, n: string) => {
    if (kindOfWord(word) !== kind) return whole;
    const i = Number(n);
    if (i === removed) return "";
    return i > removed ? whole.replace(new RegExp(`${n}$`), String(i - 1)) : whole;
  });
}

export function stripRefWords(prompt: string): string {
  return prompt.replace(/\s?@(imagen|image|video|audio)\d+\b/gi, "");
}
