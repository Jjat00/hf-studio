"use client";

import clsx from "clsx";
import {
  BookOpen,
  Brush,
  Clock,
  Folder,
  ImageIcon,
  LayoutGrid,
  Layers,
  Move,
  Rows3,
  Sparkles,
  Repeat,
  Type,
  Wand2,
  Loader2,
} from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useI18n } from "@/components/i18n-provider";
import { useGenerations } from "@/components/generations/use-generations";
import { IMAGE_TABS, VIDEO_TABS, type Mode } from "@/lib/modes";
import { cleanInput, defaultsFor, fieldsFor, type Field } from "@/lib/schema";
import { probeDuration } from "@/lib/media";
import { costShort, modelLabel, outputOf, studio, StudioError, VOICE_MODEL, type Estimate } from "@/lib/studio";
import { CostPanel, costAllowsDirectSubmit } from "./cost-panel";
import type { Generation, ModelDetail, ModelSummary } from "@/lib/types";
import { Masonry } from "@/components/masonry";
import { Chip, FieldControl, SettingCard } from "./controls";
import { EmptyState } from "./empty-state";
import { MediaSlot } from "./media-slot";
import { ModelPicker, ModelRow } from "./model-picker";

const MODE_ICON = { type: Type, image: ImageIcon, layers: Layers, wand: Wand2, clock: Clock, swap: Repeat, move: Move, sparkles: Sparkles, brush: Brush };
const detailCache = new Map<string, Promise<ModelDetail>>();

function loadDetail(id: string) {
  if (!detailCache.has(id)) {
    const p = studio.model(id);
    p.catch(() => detailCache.delete(id));
    detailCache.set(id, p);
  }
  return detailCache.get(id)!;
}

/** Recibe solo el tipo de salida: los modos llevan funciones y no pueden cruzar de servidor a cliente. */
export function Studio({ output }: { output: "video" | "image" }) {
  const { t, pick } = useI18n();
  const tabs = output === "video" ? VIDEO_TABS : IMAGE_TABS;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = tabs.find((tb) => tb.key === params.get("tab")) ?? tabs[0];
  const mode = tab.modes.find((m) => m.key === params.get("mode")) ?? tab.modes[0];

  const [models, setModels] = useState<ModelSummary[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const modelParam = params.get("model");
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [view, setView] = useState<"history" | "how">("how");
  const [keepAudio, setKeepAudio] = useState(false);
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [columns, setColumns] = useState(3);
  const idempotency = useRef<string | null>(null);
  const pendingValues = useRef<Record<string, unknown> | null>(null);
  const { items, add, loading, remove } = useGenerations();

  useEffect(() => {
    studio
      .models()
      .then((r) => setModels(r.models))
      .catch((e) => setCatalogError(e instanceof Error ? e.message : String(e)));
  }, []);

  const byId = useMemo(() => new Map(models.map((m) => [m.id, m])), [models]);
  const paramModel = modelParam ? byId.get(modelParam) : undefined;
  const modelId =
    chosen[`${tab.key}/${mode.key}`] ?? (paramModel && mode.filter(paramModel) ? paramModel.id : mode.defaultModel);
  const modeModels = models.filter(mode.filter);

  // Carga el esquema del modelo y conserva lo que siga siendo válido (prompt, medios compatibles).
  useEffect(() => {
    let alive = true;
    loadDetail(modelId)
      .then((d) => {
        if (!alive) return;
        setDetail(d);
        setErrors({});
        setFormError(null);
        const props = d.input_schema.properties ?? {};
        setValues((prev) => {
          if (pendingValues.current) {
            const v = pendingValues.current;
            pendingValues.current = null;
            return v;
          }
          const next = defaultsFor(d.input_schema);
          for (const [k, v] of Object.entries(prev)) {
            const s = props[k];
            if (!s) continue;
            if (s.enum && !s.enum.includes(v as string)) continue;
            next[k] = v;
          }
          return next;
        });
      })
      .catch((e) => alive && setFormError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [modelId]);

  const fields = useMemo(() => (detail ? fieldsFor(detail.input_schema) : []), [detail]);
  // Si el modo define etiquetas, sus ranuras salen en ese orden (p. ej. movimiento antes que personaje).
  const labelOrder = Object.keys(mode.labels ?? {});
  const rankMedia = (k: string) => (labelOrder.includes(k) ? labelOrder.indexOf(k) : labelOrder.length);
  const media = fields
    .filter((f): f is Extract<Field, { kind: "media" }> => f.kind === "media")
    .sort((a, b) => rankMedia(a.key) - rankMedia(b.key));
  const prompt = fields.find((f) => f.kind === "prompt");
  const settings = fields.filter((f) => ["enum", "range", "toggle"].includes(f.kind)) as Exclude<Field, { kind: "prompt" } | { kind: "media" }>[];
  // Opción de HF Studio (no de Higgsfield): mismo criterio que audio.supports_source_audio en la API.
  const canKeepAudio = detail?.output === "video" && "video_url" in (detail.input_schema.properties ?? {});
  const advanced = fields.filter((f) => ["text", "number", "json"].includes(f.kind)) as Exclude<Field, { kind: "prompt" } | { kind: "media" }>[];

  const setValue = useCallback((key: string, v: unknown) => {
    idempotency.current = null; // otra petición: otra clave
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)));
  }, []);

  // Duración de los videos de entrada (algunos modelos cobran por segundos de entrada).
  const [videoSecs, setVideoSecs] = useState<Record<string, number>>({});
  const videoUrls = media
    .filter((f) => f.media === "video")
    .flatMap((f) => {
      const v = values[f.key];
      return Array.isArray(v) ? (v as string[]) : typeof v === "string" ? [v] : [];
    });
  const videoKey = videoUrls.join("|");
  useEffect(() => {
    for (const url of videoKey ? videoKey.split("|") : []) {
      probeDuration(url).then((secs) => secs && setVideoSecs((prev) => (prev[url] ? prev : { ...prev, [url]: secs })));
    }
  }, [videoKey]);
  const hints: Record<string, number> = {};
  if (videoUrls.length && videoUrls.every((u) => videoSecs[u])) {
    hints.input_video_seconds = videoUrls.reduce((acc, u) => acc + videoSecs[u], 0);
  }

  // Costo antes de generar: se recalcula con debounce en cada cambio y siempre se muestra.
  const hintsKey = JSON.stringify(hints);
  const estimateKey = detail ? `${detail.id}|${JSON.stringify(cleanInput(values))}|${hintsKey}` : "";
  const [estimated, setEstimated] = useState<{ key: string; value: Estimate | null; error?: string } | null>(null);
  const current = estimated?.key === estimateKey ? estimated : null;
  const [confirmUnknown, setConfirmUnknown] = useState<string | null>(null);
  useEffect(() => {
    if (!detail) return;
    const h = JSON.parse(hintsKey) as Record<string, number>;
    const t = setTimeout(() => {
      studio
        .estimate(detail.id, cleanInput(values), h)
        .then((r) => setEstimated({ key: estimateKey, value: r }))
        .catch((e) => setEstimated({ key: estimateKey, value: null, error: e instanceof Error ? e.message : String(e) }));
    }, 500);
    return () => clearTimeout(t);
  }, [detail, values, estimateKey, hintsKey]);

  function go(next: { tab?: string; mode?: string }) {
      const sp = new URLSearchParams(params.toString());
      if (next.tab) sp.set("tab", next.tab);
      if (next.mode) sp.set("mode", next.mode);
      sp.delete("reuse");
      sp.delete("model");
      sp.delete("prompt"); // ya está en el formulario; si quedara, pisaría lo reutilizado
      router.replace(`${pathname}?${sp}`, { scroll: false });
  }

  function reuse(g: Generation) {
      if (g.model === VOICE_MODEL) {
        router.push(`/voice?reuse=${g.id}`);
        return;
      }
      for (const tb of tabs) {
        const m = tb.modes.find((x) => x.filter(byId.get(g.model) ?? ({ id: g.model, capabilities: [], output: output } as never)));
        if (!m) continue;
        pendingValues.current = g.input;
        setKeepAudio(!!g.keep_source_audio);
        setChosen((c) => ({ ...c, [`${tb.key}/${m.key}`]: g.model }));
        if (g.model === modelId) {
          setValues(g.input);
          pendingValues.current = null;
        }
        go({ tab: tb.key, mode: m.key });
        window.scrollTo({ top: 0 });
        return;
      }
  }

  // ?reuse=<id> desde la biblioteca.
  const reuseId = params.get("reuse");
  const onReuseLoaded = useEffectEvent((g: Generation) => reuse(g));
  useEffect(() => {
    if (!reuseId || models.length === 0) return;
    studio.get(reuseId).then(onReuseLoaded).catch(() => undefined);
  }, [reuseId, models.length]);

  // ?prompt=… desde Use cases: se aplica cada vez que cambia, una vez cargado un esquema con prompt.
  // Si también hay ?reuse=, manda la generación reutilizada.
  const promptParam = reuseId ? null : params.get("prompt");
  const appliedPrompt = useRef<string | null>(null);
  const onPromptParam = useEffectEvent((p: string) => {
    if (!detail?.input_schema.properties?.prompt || appliedPrompt.current === p) return;
    appliedPrompt.current = p;
    setValues((v) => ({ ...v, prompt: p }));
  });
  useEffect(() => {
    if (promptParam) onPromptParam(promptParam);
  }, [promptParam, detail]);

  // ?model=<id> desde el catálogo: si el modo actual no lo admite, salta al que sí.
  useEffect(() => {
    if (!paramModel || mode.filter(paramModel)) return;
    for (const tb of tabs) {
      const md = tb.modes.find((x) => x.filter(paramModel));
      if (!md) continue;
      const sp = new URLSearchParams({ tab: tb.key, mode: md.key, model: paramModel.id });
      router.replace(`${pathname}?${sp}`, { scroll: false });
      return;
    }
  }, [paramModel, mode, tabs, pathname, router]);

  async function submit() {
    if (!detail || submitting) return;
    // Nunca se genera sin que Jaime vea el costo: si no hay precio, se pide una segunda confirmación.
    if (!costAllowsDirectSubmit(current?.value ?? null) && confirmUnknown !== estimateKey) {
      setConfirmUnknown(estimateKey);
      return;
    }
    setConfirmUnknown(null);
    setSubmitting(true);
    setFormError(null);
    idempotency.current ??= crypto.randomUUID();
    try {
      const g = await studio.generate(detail.id, cleanInput(values), idempotency.current, canKeepAudio && keepAudio);
      add(g);
      setView("history");
      idempotency.current = null;
    } catch (e) {
      if (e instanceof StudioError && e.details) {
        const map: Record<string, string> = {};
        for (const d of e.details) map[d.path.split("/")[0]] = d.message;
        setErrors(map);
        setFormError(map["(root)"] ?? t.studio.checkFields);
      } else {
        setFormError(e instanceof Error ? e.message : String(e));
      }
      // Solo se conserva la clave si el fallo pudo ser de red (reintento seguro).
      if (e instanceof StudioError && e.status < 500) idempotency.current = null;
    } finally {
      setSubmitting(false);
    }
  }

  const history = items.filter((g) => (outputOf(g.model, byId) ?? output) === output);
  const hero = mode.hero;
  const { name } = detail ? modelLabel(detail.title) : { name: "" };
  const twoUp = media.length === 2 && media.every((m) => !m.multiple);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      {/* Panel izquierdo */}
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <nav className="hide-scrollbar flex gap-5 overflow-x-auto px-6 pt-5">
          {tabs.map((tb) => (
            <button
              key={tb.key}
              type="button"
              onClick={() => go({ tab: tb.key, mode: tb.modes[0].key })}
              className={clsx(
                "border-b-2 pb-3 text-[17px] font-medium whitespace-nowrap transition-colors",
                tb.key === tab.key ? "border-fg text-fg" : "border-transparent text-fg-3 hover:text-fg-2",
              )}
            >
              {pick(tb.label)}
            </button>
          ))}
        </nav>

        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 pt-3 pb-3">
          <HeroCard mode={mode} modelName={name} docs={detail?.docs_url} />

          {tab.modes.length > 1 && (
            <div className="grid gap-1 rounded-2xl border border-line bg-surface-2 p-1" style={{ gridTemplateColumns: `repeat(${tab.modes.length}, minmax(0, 1fr))` }}>
              {tab.modes.map((m) => {
                const Icon = MODE_ICON[m.icon];
                return (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => go({ tab: tab.key, mode: m.key })}
                    className={clsx(
                      "flex h-11 items-center justify-center gap-2 rounded-xl text-[14px] font-semibold transition-colors",
                      m.key === mode.key ? "bg-surface-5 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]" : "text-fg-3 hover:text-fg-2",
                    )}
                  >
                    <Icon className="size-4" />
                    <span className="truncate">{pick(m.label)}</span>
                  </button>
                );
              })}
            </div>
          )}

          {catalogError && <p className="rounded-2xl bg-danger/10 p-3 text-sm text-danger">{catalogError}</p>}

          {!detail ? (
            <div className="shimmer h-52 rounded-2xl" />
          ) : (
            <>
              <div className={clsx("grid gap-3", twoUp ? "grid-cols-2" : "grid-cols-1")}>
                {media.map((f) => {
                  const own = mode.labels?.[f.key];
                  const [label, hint] = own ? [pick(own[0]), pick(own[1])] : (t.media.labels[f.key] ?? [f.label, f.hint]);
                  return (
                  <MediaSlot
                    key={`${detail.id}/${f.key}`}
                    label={label}
                    hint={hint}
                    kind={f.media}
                    multiple={f.multiple}
                    max={f.max}
                    required={f.required}
                    value={values[f.key] as string | string[] | undefined}
                    onChange={(v) => setValue(f.key, v)}
                    compact={twoUp}
                    error={errors[f.key]}
                  />
                  );
                })}
              </div>

              {prompt && (
                <div className={clsx("rounded-2xl border bg-surface-3 p-4", errors.prompt ? "border-danger/60" : "border-line focus-within:border-line-2")}>
                  <textarea
                    value={(values.prompt as string) ?? ""}
                    onChange={(e) => setValue("prompt", e.target.value || undefined)}
                    onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && submit()}
                    rows={4}
                    placeholder={output === "video" ? t.studio.placeholderVideo : t.studio.placeholderImage}
                    className="w-full resize-none bg-transparent text-[16px] leading-relaxed tracking-[-0.01em] outline-none placeholder:text-fg-4"
                  />
                  <div className="flex items-center justify-between text-xs text-fg-3">
                    <span>{prompt.required ? t.studio.prompt : t.studio.promptOptional}</span>
                    <span className="font-mono">{((values.prompt as string) ?? "").length}</span>
                  </div>
                  {errors.prompt && <p className="mt-1 text-xs text-danger">{errors.prompt}</p>}
                </div>
              )}

              <ModelRow model={byId.get(detail.id)} onClick={() => setPickerOpen(true)} />

              {settings.map((f) => (
                <FieldControl key={`${detail.id}/${f.key}`} field={f} value={values[f.key]} onChange={(v) => setValue(f.key, v)} error={errors[f.key]} />
              ))}

              {canKeepAudio && (
                <SettingCard label={t.studio.keepSourceAudio}>
                  <div className="flex flex-wrap gap-1.5">
                    <Chip active={keepAudio} onClick={() => setKeepAudio(true)}>
                      {t.controls.on}
                    </Chip>
                    <Chip active={!keepAudio} onClick={() => setKeepAudio(false)}>
                      {t.controls.off}
                    </Chip>
                  </div>
                  <p className="mt-2 text-xs text-fg-3">{t.studio.keepSourceAudioHint}</p>
                </SettingCard>
              )}

              {advanced.length > 0 && (
                <details className="group rounded-2xl border border-line bg-surface-2">
                  <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-fg-2 marker:hidden">
                    {t.studio.advanced} <span className="font-normal text-fg-3">({advanced.length})</span>
                  </summary>
                  <div className="flex flex-col gap-2 px-2 pb-2">
                    {advanced.map((f) => (
                      <FieldControl key={`${detail.id}/${f.key}`} field={f} value={values[f.key]} onChange={(v) => setValue(f.key, v)} error={errors[f.key]} />
                    ))}
                  </div>
                </details>
              )}
            </>
          )}
        </div>

        <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          <CostPanel
            loading={!!detail && !current}
            estimate={current?.value ?? null}
            error={current?.error}
            needsConfirm={confirmUnknown === estimateKey}
          />
          <GenerateButton
            onClick={submit}
            busy={submitting}
            disabled={!detail}
            estimate={current?.value ?? null}
            confirming={confirmUnknown === estimateKey}
          />
        </div>
      </aside>

      {/* Panel derecho */}
      <section className="flex min-h-[70vh] min-w-0 flex-1 flex-col rounded-panel border border-line bg-surface-1">
        <div className="flex items-center gap-2 px-5 pt-4 pb-3">
          <ToolbarTab active={view === "history"} onClick={() => setView("history")} icon={<Folder className="size-4" />}>
            {t.studio.history}
          </ToolbarTab>
          <ToolbarTab active={view === "how"} onClick={() => setView("how")} icon={<BookOpen className="size-4" />}>
            {t.studio.howItWorks}
          </ToolbarTab>
          {view === "history" && history.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              {layout === "grid" && (
                <input
                  type="range"
                  min={2}
                  max={5}
                  value={7 - columns}
                  onChange={(e) => setColumns(7 - Number(e.target.value))}
                  className="hidden w-28 md:block"
                  aria-label={t.studio.size}
                />
              )}
              <ToolbarTab active={layout === "list"} onClick={() => setLayout("list")} icon={<Rows3 className="size-4" />}>
                {t.studio.list}
              </ToolbarTab>
              <ToolbarTab active={layout === "grid"} onClick={() => setLayout("grid")} icon={<LayoutGrid className="size-4" />}>
                {t.studio.grid}
              </ToolbarTab>
            </div>
          )}
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-5 pb-5">
          {view === "how" || (!loading && history.length === 0) ? (
            <EmptyState empty={tab.empty} art={hero.art} notes={view === "how" ? detail?.notes : undefined} />
          ) : loading ? (
            <div className="grid grid-cols-2 gap-4 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="shimmer aspect-video rounded-2xl" />
              ))}
            </div>
          ) : layout === "grid" ? (
            <Masonry
              items={history}
              itemKey={(g) => g.id}
              maxColumns={columns}
              minColumnWidth={200}
              render={(g) => <GenerationCard g={g} layout="grid" models={byId} onReuse={reuse} onDelete={remove} />}
            />
          ) : (
            <div className="flex flex-col gap-3">
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="list" models={byId} onReuse={reuse} onDelete={remove} />
              ))}
            </div>
          )}
        </div>
      </section>

      <ModelPicker
        open={pickerOpen}
        models={modeModels}
        selected={modelId}
        onSelect={(id) => {
          idempotency.current = null;
          setChosen((c) => ({ ...c, [`${tab.key}/${mode.key}`]: id }));
        }}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );
}

const TONES: Record<Mode["hero"]["tone"], string> = {
  lime: "from-black/80 via-black/30 to-transparent",
  pink: "from-black/80 via-black/30 to-transparent",
  blue: "from-black/80 via-black/30 to-transparent",
  amber: "from-black/80 via-black/30 to-transparent",
  violet: "from-black/80 via-black/30 to-transparent",
};

function HeroCard({ mode, modelName, docs }: { mode: Mode; modelName: string; docs?: string }) {
  const { t, pick } = useI18n();
  const title = pick(mode.hero.title);
  const subtitle = pick(mode.hero.subtitle);
  return (
    <div className="grain relative h-[196px] shrink-0 overflow-hidden rounded-2xl bg-surface-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={mode.hero.art} alt="" className="absolute inset-0 size-full object-cover" />
      <div className={clsx("absolute inset-0 bg-gradient-to-t", TONES[mode.hero.tone])} />
      {docs && (
        <a
          href={docs}
          target="_blank"
          rel="noreferrer"
          className="absolute top-3 right-3 flex items-center gap-1.5 rounded-xl bg-black/55 px-3 py-1.5 text-[14px] font-medium backdrop-blur-md hover:bg-black/70"
        >
          <BookOpen className="size-4" /> {t.studio.howItWorks}
        </a>
      )}
      <div className="absolute bottom-4 left-4 right-4">
        <p className="headline text-[28px] text-lime drop-shadow">{title}</p>
        <p className="mt-1 text-[15px] font-medium text-white/85">{modelName ? `${modelName} · ${subtitle}` : subtitle}</p>
      </div>
    </div>
  );
}

function GenerateButton({
  onClick,
  busy,
  disabled,
  estimate,
  confirming,
}: {
  onClick: () => void;
  busy: boolean;
  disabled: boolean;
  estimate: Estimate | null;
  confirming: boolean;
}) {
  const { t } = useI18n();
  const short = costShort(estimate);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className="flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] transition-[filter,transform] hover:brightness-105 active:translate-y-px disabled:opacity-50"
    >
      {busy ? (
        <Loader2 className="size-6 animate-spin" />
      ) : confirming ? (
        t.studio.generateAnyway
      ) : (
        t.studio.generate
      )}
      {!busy && !confirming && short && (
        <span className="flex items-center gap-1 text-[19px]">
          {estimate?.kind === "exact" && <Sparkles className="size-5 fill-ink" />}
          {short}
        </span>
      )}
    </button>
  );
}

function ToolbarTab({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "flex h-10 items-center gap-2 rounded-xl px-3 text-[15px] font-medium transition-colors",
        active ? "bg-surface-4 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]" : "text-fg-3 hover:text-fg-2",
      )}
    >
      {icon}
      {children}
    </button>
  );
}
