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
import { useGenerations } from "@/components/generations/use-generations";
import { IMAGE_TABS, VIDEO_TABS, type Mode } from "@/lib/modes";
import { cleanInput, defaultsFor, fieldsFor, type Field } from "@/lib/schema";
import { modelLabel, studio, StudioError } from "@/lib/studio";
import type { Generation, ModelDetail, ModelSummary } from "@/lib/types";
import { FieldControl } from "./controls";
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
  const tabs = output === "video" ? VIDEO_TABS : IMAGE_TABS;
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = tabs.find((t) => t.key === params.get("tab")) ?? tabs[0];
  const mode = tab.modes.find((m) => m.key === params.get("mode")) ?? tab.modes[0];

  const [models, setModels] = useState<ModelSummary[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const modelParam = params.get("model");
  const [detail, setDetail] = useState<ModelDetail | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [estimated, setEstimated] = useState<{ key: string; credits: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [view, setView] = useState<"history" | "how">("history");
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [columns, setColumns] = useState(3);
  const idempotency = useRef<string | null>(null);
  const pendingValues = useRef<Record<string, unknown> | null>(null);
  const { items, add, loading } = useGenerations();

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
  const advanced = fields.filter((f) => ["text", "number", "json"].includes(f.kind)) as Exclude<Field, { kind: "prompt" } | { kind: "media" }>[];

  const setValue = useCallback((key: string, v: unknown) => {
    idempotency.current = null; // otra petición: otra clave
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)));
  }, []);

  // Estimación de créditos con debounce; si la entrada aún no es válida, simplemente no se muestra.
  const estimateKey = detail ? `${detail.id}:${JSON.stringify(cleanInput(values))}` : "";
  const estimate = estimated?.key === estimateKey ? estimated.credits : null;
  useEffect(() => {
    if (!detail) return;
    const t = setTimeout(() => {
      studio
        .estimate(detail.id, cleanInput(values))
        .then((r) => setEstimated({ key: estimateKey, credits: String(parseFloat(r.credits)) }))
        .catch(() => undefined);
    }, 700);
    return () => clearTimeout(t);
  }, [detail, values, estimateKey]);

  function go(next: { tab?: string; mode?: string }) {
      const sp = new URLSearchParams(params.toString());
      if (next.tab) sp.set("tab", next.tab);
      if (next.mode) sp.set("mode", next.mode);
      sp.delete("reuse");
      sp.delete("model");
      router.replace(`${pathname}?${sp}`, { scroll: false });
  }

  function reuse(g: Generation) {
      for (const t of tabs) {
        const m = t.modes.find((x) => x.filter(byId.get(g.model) ?? ({ id: g.model, capabilities: [], output: output } as never)));
        if (!m) continue;
        pendingValues.current = g.input;
        setChosen((c) => ({ ...c, [`${t.key}/${m.key}`]: g.model }));
        if (g.model === modelId) {
          setValues(g.input);
          pendingValues.current = null;
        }
        go({ tab: t.key, mode: m.key });
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

  // ?model=<id> desde el catálogo: si el modo actual no lo admite, salta al que sí.
  useEffect(() => {
    if (!paramModel || mode.filter(paramModel)) return;
    for (const t of tabs) {
      const md = t.modes.find((x) => x.filter(paramModel));
      if (!md) continue;
      const sp = new URLSearchParams({ tab: t.key, mode: md.key, model: paramModel.id });
      router.replace(`${pathname}?${sp}`, { scroll: false });
      return;
    }
  }, [paramModel, mode, tabs, pathname, router]);

  async function submit() {
    if (!detail || submitting) return;
    setSubmitting(true);
    setFormError(null);
    idempotency.current ??= crypto.randomUUID();
    try {
      const g = await studio.generate(detail.id, cleanInput(values), idempotency.current);
      add(g);
      setView("history");
      idempotency.current = null;
    } catch (e) {
      if (e instanceof StudioError && e.details) {
        const map: Record<string, string> = {};
        for (const d of e.details) map[d.path.split("/")[0]] = d.message;
        setErrors(map);
        setFormError(map["(raíz)"] ?? "Check the highlighted fields");
      } else {
        setFormError(e instanceof Error ? e.message : String(e));
      }
      // Solo se conserva la clave si el fallo pudo ser de red (reintento seguro).
      if (e instanceof StudioError && e.status < 500) idempotency.current = null;
    } finally {
      setSubmitting(false);
    }
  }

  const history = items.filter((g) => (byId.get(g.model)?.output ?? output) === output);
  const hero = mode.hero;
  const { name } = detail ? modelLabel(detail.title) : { name: "" };
  const twoUp = media.length === 2 && media.every((m) => !m.multiple);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      {/* Panel izquierdo */}
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <nav className="flex gap-5 px-6 pt-5">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => go({ tab: t.key, mode: t.modes[0].key })}
              className={clsx(
                "border-b-2 pb-3 text-[17px] font-medium whitespace-nowrap transition-colors",
                t.key === tab.key ? "border-fg text-fg" : "border-transparent text-fg-3 hover:text-fg-2",
              )}
            >
              {t.label}
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
                    <span className="truncate">{m.label}</span>
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
                {media.map((f) => (
                  <MediaSlot
                    key={`${detail.id}/${f.key}`}
                    label={mode.labels?.[f.key]?.[0] ?? f.label}
                    hint={mode.labels?.[f.key]?.[1] ?? f.hint}
                    kind={f.media}
                    multiple={f.multiple}
                    max={f.max}
                    required={f.required}
                    value={values[f.key] as string | string[] | undefined}
                    onChange={(v) => setValue(f.key, v)}
                    compact={twoUp}
                    error={errors[f.key]}
                  />
                ))}
              </div>

              {prompt && (
                <div className={clsx("rounded-2xl border bg-surface-3 p-4", errors.prompt ? "border-danger/60" : "border-line focus-within:border-line-2")}>
                  <textarea
                    value={(values.prompt as string) ?? ""}
                    onChange={(e) => setValue("prompt", e.target.value || undefined)}
                    onKeyDown={(e) => (e.metaKey || e.ctrlKey) && e.key === "Enter" && submit()}
                    rows={4}
                    placeholder={output === "video" ? "Describe the scene, the camera and the motion…" : "Describe the image: subject, light, lens, style…"}
                    className="w-full resize-none bg-transparent text-[16px] leading-relaxed tracking-[-0.01em] outline-none placeholder:text-fg-4"
                  />
                  <div className="flex items-center justify-between text-xs text-fg-3">
                    <span>{prompt.required ? "Prompt" : "Prompt · optional"}</span>
                    <span className="font-mono">{((values.prompt as string) ?? "").length}</span>
                  </div>
                  {errors.prompt && <p className="mt-1 text-xs text-danger">{errors.prompt}</p>}
                </div>
              )}

              <ModelRow model={byId.get(detail.id)} onClick={() => setPickerOpen(true)} />

              {settings.map((f) => (
                <FieldControl key={`${detail.id}/${f.key}`} field={f} value={values[f.key]} onChange={(v) => setValue(f.key, v)} error={errors[f.key]} />
              ))}

              {advanced.length > 0 && (
                <details className="group rounded-2xl border border-line bg-surface-2">
                  <summary className="cursor-pointer list-none px-4 py-3 text-sm font-semibold text-fg-2 marker:hidden">
                    Advanced <span className="font-normal text-fg-3">({advanced.length})</span>
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

        <div className="border-t border-line p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          <GenerateButton onClick={submit} busy={submitting} disabled={!detail} estimate={estimate} />
        </div>
      </aside>

      {/* Panel derecho */}
      <section className="flex min-h-[70vh] min-w-0 flex-1 flex-col rounded-panel border border-line bg-surface-1">
        <div className="flex items-center gap-2 px-5 pt-4 pb-3">
          <ToolbarTab active={view === "history"} onClick={() => setView("history")} icon={<Folder className="size-4" />}>
            History
          </ToolbarTab>
          <ToolbarTab active={view === "how"} onClick={() => setView("how")} icon={<BookOpen className="size-4" />}>
            How it works
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
                  aria-label="Tamaño"
                />
              )}
              <ToolbarTab active={layout === "list"} onClick={() => setLayout("list")} icon={<Rows3 className="size-4" />}>
                List
              </ToolbarTab>
              <ToolbarTab active={layout === "grid"} onClick={() => setLayout("grid")} icon={<LayoutGrid className="size-4" />}>
                Grid
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
            <div
              className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:[grid-template-columns:repeat(var(--cols),minmax(0,1fr))]"
              style={{ "--cols": columns } as React.CSSProperties}
            >
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="grid" models={byId} onReuse={reuse} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="list" models={byId} onReuse={reuse} />
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
          <BookOpen className="size-4" /> How it works
        </a>
      )}
      <div className="absolute bottom-4 left-4 right-4">
        <p className="headline text-[28px] text-lime drop-shadow">{modelName ? `${mode.hero.title}` : mode.hero.title}</p>
        <p className="mt-1 text-[15px] font-medium text-white/85">{modelName ? `${modelName} · ${mode.hero.subtitle}` : mode.hero.subtitle}</p>
      </div>
    </div>
  );
}

function GenerateButton({ onClick, busy, disabled, estimate }: { onClick: () => void; busy: boolean; disabled: boolean; estimate: string | null }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className="flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] transition-[filter,transform] hover:brightness-105 active:translate-y-px disabled:opacity-50"
    >
      {busy ? <Loader2 className="size-6 animate-spin" /> : "Generate"}
      {!busy && estimate && (
        <span className="flex items-center gap-1 text-[19px]">
          <Sparkles className="size-5 fill-ink" />
          {estimate}
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
