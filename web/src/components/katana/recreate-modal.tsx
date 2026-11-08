"use client";

import clsx from "clsx";
import { ArrowRight, Check, ChevronDown, Film, ImagePlus, Loader2, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Chip } from "@/components/studio/controls";
import { formatUsd, studio, type KatanaPlanAsk, type KatanaPreset, type KatanaProject } from "@/lib/studio";
import { KatanaModal, MediaGrid, SourceTabs, type Picked, type SourceId } from "./media-sources";

const ASPECTS = ["9:16", "16:9", "1:1", "4:3", "3:4"];
const RESOLUTIONS: KatanaPlanAsk["resolution"][] = ["480p", "720p", "1080p"];
const LANGUAGES = ["es", "en", "pt", "fr"];
/** El plan acepta hasta 5 fotos del sujeto (algunos presets de Higgsfield admiten 10). */
const MAX_SUBJECTS = 5;

type Step = "reference" | "assets" | "instructions" | "plan";

function errorText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

/** «Recrear plantilla» como en higgsfield.ai/katana: Referencia → Recursos → Instrucciones; aquí además se cotiza
 * el plan de Claude, se aprueba y se abre el Space (nada se genera sin el OK del usuario). */
export function RecreateModal({
  presets,
  preset: initialPreset,
  project: initialProject,
  onClose,
  onProject,
}: {
  presets: KatanaPreset[];
  preset?: KatanaPreset | null;
  project?: KatanaProject | null;
  onClose: () => void;
  onProject: (p: KatanaProject) => void;
}) {
  const { t } = useI18n();
  const k = t.katana;
  const fromProject = initialProject?.analysis ? initialProject : null;
  const [step, setStep] = useState<Step>(fromProject ? (fromProject.plan ? "plan" : "assets") : "reference");
  const [reference, setReference] = useState<Picked | null>(
    initialPreset
      ? { key: `preset:${initialPreset.id}`, url: initialPreset.video_url, title: initialPreset.name, poster: initialPreset.thumbnail_url || undefined, preset: initialPreset }
      : fromProject
        ? { key: `project:${fromProject.id}`, url: fromProject.reference_url, title: fromProject.title }
        : null,
  );
  const [project, setProject] = useState<KatanaProject | null>(fromProject);
  const [refSource, setRefSource] = useState<SourceId>("presets");
  const [assetSource, setAssetSource] = useState<SourceId>("uploads");
  const [assets, setAssets] = useState<Picked[]>([]);
  const [brief, setBrief] = useState("");
  const [aspect, setAspect] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [resolution, setResolution] = useState<KatanaPlanAsk["resolution"]>("720p");
  const [maxClips, setMaxClips] = useState(3);
  const [maxSeconds, setMaxSeconds] = useState(30);
  const [music, setMusic] = useState<KatanaPlanAsk["music"]>("reference");
  const [language, setLanguage] = useState("es");
  const [busy, setBusy] = useState<"" | "analyze" | "estimate" | "plan" | "drop">("");
  const [error, setError] = useState("");
  const [quoted, setQuoted] = useState<{ max_usd: number; available: boolean; sig: string } | null>(null);
  const [planned, setPlanned] = useState<{ cost_usd: number; generated_seconds: number; warnings: string[] } | null>(null);
  const planKey = useRef("");
  const dropInput = useRef<HTMLInputElement>(null);

  const preset = reference?.preset ?? presets.find((p) => p.id === project?.preset) ?? null;
  const maxAssets = Math.min(MAX_SUBJECTS, preset?.max_images ?? MAX_SUBJECTS);
  const a = project?.analysis;

  const ask = (): KatanaPlanAsk => ({
    subject_urls: assets.map((x) => x.url),
    brief,
    ...(aspect ? { aspect } : {}),
    ...(duration ? { duration } : {}),
    resolution,
    max_clips: maxClips,
    max_video_seconds: maxSeconds,
    music,
    language,
    ...(preset?.description ? { preset_context: preset.description } : {}),
  });
  // Cualquier cambio invalida la cotización (y su clave de idempotencia).
  const sig = JSON.stringify([project?.id, assets.map((x) => x.url), brief, aspect, duration, resolution, maxClips, maxSeconds, music, language]);
  const quote = quoted && quoted.sig === sig ? quoted : null;

  function chooseReference(p: Picked) {
    setReference(p);
    if (project && project.reference_url !== p.url) {
      setProject(null);
      setPlanned(null);
    }
  }

  async function dropReference(files: FileList | null) {
    const f = files?.[0];
    if (!f || !f.type.startsWith("video/")) return;
    setBusy("drop");
    setError("");
    try {
      const up = await studio.upload(f);
      chooseReference({ key: `up:${up.id}`, url: up.url, title: f.name.replace(/\.[^.]+$/, "") });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  /** Continuar desde Referencia: analiza (gratis) si la referencia cambió. */
  async function confirmReference() {
    if (!reference) return;
    if (project && project.reference_url === reference.url) return setStep("assets");
    setBusy("analyze");
    setError("");
    try {
      const p = await studio.katanaCreate(reference.url, reference.title);
      setProject(p);
      onProject(p);
      setStep("assets");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  function toggleAsset(p: Picked) {
    setAssets((list) =>
      list.some((x) => x.key === p.key) ? list.filter((x) => x.key !== p.key) : list.length >= maxAssets ? list : [...list, p],
    );
  }

  async function estimate() {
    if (!project) return;
    setBusy("estimate");
    setError("");
    try {
      const q = await studio.katanaPlanEstimate(project.id, ask());
      planKey.current = "";
      setQuoted({ max_usd: q.max_usd, available: q.available, sig });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  async function plan() {
    if (!project || !quote) return;
    setBusy("plan");
    setError("");
    if (!planKey.current) planKey.current = crypto.randomUUID();
    try {
      const r = await studio.katanaPlan(project.id, { ...ask(), max_usd: quote.max_usd }, planKey.current);
      setProject(r);
      onProject(r);
      setPlanned({ cost_usd: r.cost_usd, generated_seconds: r.generated_seconds, warnings: r.warnings });
      setStep("plan");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  const done: Record<Step, boolean> = {
    reference: !!project && project.reference_url === reference?.url,
    assets: assets.length > 0 || !!project?.plan,
    instructions: !!project?.plan,
    plan: !!project?.space_id,
  };
  const reachable: Record<Step, boolean> = {
    reference: true,
    assets: done.reference,
    instructions: done.reference && assets.length > 0,
    plan: !!project?.plan,
  };
  const steps: [Step, string][] = [
    ["reference", k.stepReference],
    ["assets", k.stepAssets],
    ["instructions", k.stepInstructions],
    ...(project?.plan ? ([["plan", k.stepPlan]] as [Step, string][]) : []),
  ];

  const aside = (
    <ul className="space-y-1">
      {steps.map(([id, label]) => (
        <li key={id}>
          <button type="button" disabled={!reachable[id] || !!busy} onClick={() => setStep(id)}
            className={clsx("flex h-12 w-full items-center gap-3 rounded-xl px-3 text-[17px] font-medium transition disabled:opacity-60",
              step === id ? "bg-white/10 text-fg" : "text-fg-2 hover:bg-white/5")}>
            <span className={clsx("flex size-5 items-center justify-center rounded-full border-[1.5px]", done[id] ? "border-lime text-lime" : "border-fg-3")}>
              {done[id] && <Check className="size-3" strokeWidth={3} />}
            </span>
            {label}
          </button>
        </li>
      ))}
    </ul>
  );

  const primary = "flex h-12 items-center justify-center gap-2 rounded-xl bg-lime px-6 text-[17px] font-semibold text-black transition hover:bg-lime-400 disabled:opacity-50";
  const secondary = "h-12 rounded-xl bg-surface-4 px-6 text-[17px] font-semibold hover:bg-white/10 disabled:opacity-50";

  let footer: React.ReactNode = null;
  if (step === "reference")
    footer = (
      <button type="button" className={primary} disabled={!reference || !!busy} onClick={confirmReference}>
        {busy === "analyze" && <Loader2 className="size-4 animate-spin" />}
        {busy === "analyze" ? k.analyzing : k.continue}
      </button>
    );
  else if (step === "assets")
    footer = (
      <>
        <button type="button" className={secondary} onClick={() => setStep("reference")}>{k.back}</button>
        <button type="button" className={primary} disabled={!assets.length} onClick={() => setStep("instructions")}>{k.continue}</button>
      </>
    );
  else if (step === "instructions")
    footer = (
      <>
        <button type="button" className={secondary} disabled={!!busy} onClick={() => setStep("assets")}>{k.back}</button>
        {!quote ? (
          <button type="button" className={primary} disabled={!!busy || !assets.length} onClick={estimate}>
            {busy === "estimate" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {k.estimate}
          </button>
        ) : (
          <button type="button" className={primary} disabled={!!busy || !quote.available} onClick={plan}>
            {busy === "plan" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {busy === "plan" ? k.planning : k.approvePlan}
          </button>
        )}
      </>
    );
  else if (step === "plan")
    footer = project?.space_id ? (
      <Link href={`/spaces/${project.space_id}`} className={primary}>
        <Film className="size-4" />
        {k.openSpace}
        <ArrowRight className="size-4" />
      </Link>
    ) : null;

  return (
    <KatanaModal title={k.recreateTitle} onClose={() => !busy && onClose()} aside={aside} footer={footer}>
      {/* Pasos en móvil */}
      <div className="mb-4 flex gap-1 overflow-x-auto md:hidden">
        {steps.map(([id, label]) => (
          <button key={id} type="button" disabled={!reachable[id] || !!busy} onClick={() => setStep(id)}
            className={clsx("h-9 shrink-0 rounded-full px-3 text-sm", step === id ? "bg-white text-black" : "bg-surface-4 text-fg-2 disabled:opacity-50")}>
            {label}
          </button>
        ))}
      </div>

      {error && <p className="mb-4 rounded-2xl border border-danger/50 bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {step === "reference" && (
        <div className="space-y-5">
          <h3 className="text-2xl font-semibold">{k.pickReference}</h3>
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); void dropReference(e.dataTransfer.files); }}
            className="rounded-3xl bg-surface-4/60 p-4">
            <div className="flex h-72 items-center justify-center rounded-2xl border-2 border-dashed border-white/15 md:h-80">
              {busy === "drop" ? (
                <Loader2 className="size-6 animate-spin text-fg-3" />
              ) : reference ? (
                <div className="relative h-56 max-w-[80%] -rotate-3 overflow-hidden rounded-xl border border-white/20 shadow-2xl md:h-64">
                  <video key={reference.url} src={reference.url} poster={reference.poster} muted loop autoPlay playsInline className="h-full w-auto object-cover" />
                  {reference.title && <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-6 text-sm font-semibold">{reference.title}</span>}
                </div>
              ) : (
                <button type="button" onClick={() => dropInput.current?.click()} className="flex flex-col items-center gap-3 text-fg-2">
                  <span className="flex size-16 items-center justify-center rounded-full bg-surface-5"><Film className="size-6" /></span>
                  <span className="text-lg font-semibold text-fg">{k.dropReference}</span>
                </button>
              )}
            </div>
            <input ref={dropInput} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
              onChange={(e) => void dropReference(e.target.files)} />
          </div>
          {preset?.description && <p className="text-sm text-fg-3">{preset.description}</p>}
          <SourceTabs sources={["presets", "uploads", "generations", "likes"]} active={refSource} onChange={setRefSource} />
          <MediaGrid source={refSource} kind="video" presets={presets} selected={reference ? [reference.key] : []}
            onPick={chooseReference} onError={setError} />
        </div>
      )}

      {step === "assets" && (
        <div className="space-y-5">
          <h3 className="text-2xl font-semibold">{k.assetsTitle}</h3>
          <div className="rounded-3xl bg-surface-4/60 p-4">
            <div className="flex min-h-72 items-center justify-center rounded-2xl border-2 border-dashed border-white/15 p-4 md:min-h-80">
              {assets.length ? (
                <div className="flex flex-wrap items-center justify-center gap-3">
                  {assets.map((x, i) => (
                    <div key={x.key} className={clsx("relative h-44 w-32 overflow-hidden rounded-xl border border-white/20 shadow-xl", i % 2 ? "rotate-2" : "-rotate-2")}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={x.url} alt="" className="size-full object-cover" />
                      <button type="button" onClick={() => toggleAsset(x)} aria-label={k.remove}
                        className="absolute right-1.5 top-1.5 flex size-6 items-center justify-center rounded-full bg-black/70"><X className="size-3.5" /></button>
                    </div>
                  ))}
                  <span className="w-full text-center text-sm text-fg-3">{k.assetsCount(assets.length, maxAssets)}</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 text-center">
                  <span className="flex size-20 items-center justify-center rounded-full bg-surface-5"><ImagePlus className="size-7" /></span>
                  <span className="text-2xl font-semibold">{k.addAssets}</span>
                  <span className="text-fg-3">{k.addAssetsHint}</span>
                </div>
              )}
            </div>
          </div>
          <SourceTabs sources={["uploads", "influencer", "generations", "likes"]} active={assetSource} onChange={setAssetSource} />
          <MediaGrid source={assetSource} kind="image" selected={assets.map((x) => x.key)} onPick={toggleAsset} onError={setError} />
        </div>
      )}

      {step === "instructions" && a && (
        <div className="space-y-5">
          <h3 className="text-2xl font-semibold">{k.instructionsTitle}</h3>
          <label className="block space-y-2">
            <span className="text-[17px] font-semibold">{k.instructions} <span className="font-normal text-fg-3">{k.optional}</span></span>
            <textarea value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000} rows={5}
              placeholder={k.instructionsPlaceholder}
              className="w-full resize-y rounded-2xl bg-surface-4 p-4 text-lg outline-none placeholder:text-fg-3 focus:ring-1 focus:ring-white/20" />
          </label>

          <Fold title={k.advanced}>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={k.aspect}>
                <div className="flex flex-wrap gap-1.5">
                  {ASPECTS.map((x) => <Chip key={x} active={(aspect ?? a.aspect) === x} onClick={() => setAspect(x)}>{x}</Chip>)}
                </div>
              </Field>
              <Field label={k.duration}>
                <input type="number" min={3} max={60} step={0.5}
                  value={duration ?? Math.min(30, Math.max(5, Math.round(a.energy.duration * 10) / 10))}
                  onChange={(e) => setDuration(Number(e.target.value) || null)} className="h-9 w-24 rounded-lg bg-surface-4 px-2 text-sm" />
              </Field>
              <Field label={k.resolution}>
                <div className="flex gap-1.5">{RESOLUTIONS.map((r) => <Chip key={r} active={resolution === r} onClick={() => setResolution(r)}>{r}</Chip>)}</div>
              </Field>
              <Field label={`${k.maxClips} · ${k.maxSeconds}`}>
                <div className="flex items-center gap-2">
                  <input type="number" min={1} max={6} value={maxClips} onChange={(e) => setMaxClips(Math.min(6, Math.max(1, Number(e.target.value) || 1)))}
                    className="h-9 w-16 rounded-lg bg-surface-4 px-2 text-sm" />
                  <input type="number" min={4} max={90} value={maxSeconds} onChange={(e) => setMaxSeconds(Math.min(90, Math.max(4, Number(e.target.value) || 4)))}
                    className="h-9 w-20 rounded-lg bg-surface-4 px-2 text-sm" />
                </div>
              </Field>
              <Field label={k.music}>
                <div className="flex gap-1.5">
                  <Chip active={music === "reference"} onClick={() => setMusic("reference")}>{k.musicRef}</Chip>
                  <Chip active={music === "none"} onClick={() => setMusic("none")}>{k.musicNone}</Chip>
                </div>
              </Field>
              <Field label={k.language}>
                <div className="flex gap-1.5">{LANGUAGES.map((l) => <Chip key={l} active={language === l} onClick={() => setLanguage(l)}>{l}</Chip>)}</div>
              </Field>
            </div>
          </Fold>

          <Fold title={k.analysis}>
            <Analysis project={project!} />
          </Fold>

          {quote && (
            <p className={clsx("rounded-2xl border p-4 text-sm", quote.available ? "border-lime/40 bg-lime/5" : "border-danger/50 bg-danger/10 text-danger")}>
              {quote.available ? k.planCost(formatUsd(quote.max_usd)) : k.noClaude}
            </p>
          )}
        </div>
      )}

      {step === "plan" && project?.plan && (
        <div className="space-y-5">
          <h3 className="text-2xl font-semibold">{project.plan.title}</h3>
          <dl className="space-y-4 text-[15px]">
            <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.trick}</dt><dd>{project.plan.trick}</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.concept}</dt><dd>{project.plan.concept}</dd></div>
            <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.look}</dt><dd>{project.plan.look} · {project.plan.aspect} · {project.plan.duration} s</dd></div>
            {!!project.plan.locations.length && (
              <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.locations}</dt>
                {project.plan.locations.map((l) => <dd key={l.id} className="line-clamp-2"><b>{l.id}</b> {l.prompt}</dd>)}</div>
            )}
            {!!project.plan.stills.length && (
              <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.stills}</dt>
                {project.plan.stills.map((s) => <dd key={s.id} className="line-clamp-2"><b>{s.id}</b> {s.prompt}</dd>)}</div>
            )}
            <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.clips}</dt>
              {project.plan.clips.map((c) => <dd key={c.id} className="line-clamp-3"><b>{c.id}</b> ({c.duration} s) {c.prompt}</dd>)}</div>
            {project.plan.notes && <div><dt className="text-xs uppercase tracking-wide text-fg-3">{k.notes}</dt><dd>{project.plan.notes}</dd></div>}
          </dl>
          {planned && (
            <p className="text-xs text-fg-3">
              {k.spent(formatUsd(planned.cost_usd))} · {k.generatedSeconds(planned.generated_seconds)}
              {planned.warnings.map((w) => <span key={w} className="block text-warning">{w}</span>)}
            </p>
          )}
          {project.space_id && <p className="text-sm text-fg-3">{k.spaceHint}</p>}
        </div>
      )}
    </KatanaModal>
  );
}

function Fold({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="group rounded-2xl bg-surface-4/60">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-[15px] font-semibold">
        {title}
        <ChevronDown className="size-4 text-fg-3 transition group-open:rotate-180" />
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-fg-3">{label}</p>
      {children}
    </div>
  );
}

function Analysis({ project }: { project: KatanaProject }) {
  const { t } = useI18n();
  const k = t.katana;
  const a = project.analysis!;
  const rates = a.energy.rates ?? {};
  return (
    <div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span>{a.energy.duration.toFixed(1)} s · {a.probe.width}×{a.probe.height} · {a.aspect}</span>
        <span>{a.energy.shots.length} {k.shots}</span>
        <span>{rates.cuts_per_s?.toFixed(2)}{k.perSecond} {k.cuts}</span>
        <span>{rates.flashes_per_s?.toFixed(2)}{k.perSecond} {k.flashes}</span>
        <span>{rates.shakes_per_s?.toFixed(2)}{k.perSecond} {k.shakes}</span>
        <span>{rates.camera_moves_per_s?.toFixed(2)}{k.perSecond} {k.moves}</span>
        <span>{rates.hits_per_s?.toFixed(2)}{k.perSecond} {k.hits}</span>
        {a.energy.tempo_bpm && <span>{a.energy.tempo_bpm} {k.bpm}</span>}
      </div>
      <div className="mt-3 flex h-10 items-end gap-px">
        {a.energy.curve.map((v, i) => (
          <div key={i} className="flex-1 rounded-t bg-lime/70" style={{ height: `${Math.max(4, v * 100)}%` }} title={`${i}s`} />
        ))}
      </div>
      <p className="mt-3 text-xs text-fg-3">{k.sheets} ({a.sheets.length})</p>
      <div className="mt-2 grid gap-2">
        {a.sheets.map((s) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={s.file} src={studio.katanaFile(project.id, "sheets", s.file)} alt={`${s.start}-${s.end}s`} className="w-full rounded-lg" loading="lazy" />
        ))}
      </div>
    </div>
  );
}
