"use client";

import clsx from "clsx";
import { ArrowRight, Film, ImagePlus, Loader2, Sparkles, Swords, Trash2, Upload, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Chip, SettingCard } from "@/components/studio/controls";
import { formatUsd, studio, type KatanaPlanAsk, type KatanaPreset, type KatanaProject } from "@/lib/studio";

const ASPECTS = ["9:16", "16:9", "1:1", "4:3", "3:4"];
const RESOLUTIONS: KatanaPlanAsk["resolution"][] = ["480p", "720p", "1080p"];
const LANGUAGES = ["es", "en", "pt", "fr"];

function errorText(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

/** Katana: referencia → análisis gratis → fotos y encargo → plan de Claude (con su tope) → Space para cotizar y generar. */
export function KatanaStudio() {
  const { t } = useI18n();
  const k = t.katana;
  const [presets, setPresets] = useState<KatanaPreset[]>([]);
  const [projects, setProjects] = useState<KatanaProject[]>([]);
  const [project, setProject] = useState<KatanaProject | null>(null);
  const [busy, setBusy] = useState<"" | "analyze" | "estimate" | "plan" | "photo">("");
  const [error, setError] = useState("");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [brief, setBrief] = useState("");
  const [aspect, setAspect] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [resolution, setResolution] = useState<KatanaPlanAsk["resolution"]>("720p");
  const [maxClips, setMaxClips] = useState(3);
  const [maxSeconds, setMaxSeconds] = useState(30);
  const [music, setMusic] = useState<KatanaPlanAsk["music"]>("reference");
  const [language, setLanguage] = useState("es");
  const [quoted, setQuoted] = useState<{ max_usd: number; available: boolean; sig: string } | null>(null);
  const [planned, setPlanned] = useState<{ cost_usd: number; generated_seconds: number; warnings: string[] } | null>(null);
  const planKey = useRef<string>("");
  const refInput = useRef<HTMLInputElement>(null);
  const photoInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    studio.katanaPresets().then((r) => setPresets(r.presets)).catch(() => {});
    studio.katanaProjects().then((r) => setProjects(r.projects)).catch(() => {});
  }, []);

  const ask = (): KatanaPlanAsk => ({
    subject_urls: subjects,
    brief,
    ...(aspect ? { aspect } : {}),
    ...(duration ? { duration } : {}),
    resolution,
    max_clips: maxClips,
    max_video_seconds: maxSeconds,
    music,
    language,
  });

  // Cualquier cambio del encargo invalida la cotización del plan (y su clave de idempotencia).
  const sig = JSON.stringify([project?.id, subjects, brief, aspect, duration, resolution, maxClips, maxSeconds, music, language]);
  const quote = quoted && quoted.sig === sig ? quoted : null;

  async function analyze(url: string, title?: string) {
    setBusy("analyze");
    setError("");
    setPlanned(null);
    try {
      const p = await studio.katanaCreate(url, title);
      setProject(p);
      setProjects((list) => [p, ...list.filter((x) => x.id !== p.id)]);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  async function uploadReference(file: File) {
    setBusy("analyze");
    setError("");
    try {
      const up = await studio.upload(file);
      await analyze(up.url, file.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setError(errorText(e));
      setBusy("");
    }
  }

  async function addPhotos(files: FileList) {
    setBusy("photo");
    setError("");
    try {
      const urls: string[] = [];
      for (const f of Array.from(files).slice(0, 5 - subjects.length)) urls.push((await studio.upload(f)).url);
      setSubjects((s) => [...s, ...urls].slice(0, 5));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
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
      setPlanned({ cost_usd: r.cost_usd, generated_seconds: r.generated_seconds, warnings: r.warnings });
      setProjects((list) => [r, ...list.filter((x) => x.id !== r.id)]);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  }

  async function open(id: string) {
    setError("");
    setPlanned(null);
    try {
      setProject(await studio.katanaProject(id));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function remove(id: string) {
    await studio.katanaDelete(id).catch(() => {});
    setProjects((list) => list.filter((x) => x.id !== id));
    if (project?.id === id) setProject(null);
  }

  const a = project?.analysis;
  const rates = a?.energy.rates ?? {};

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
      <header className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Swords className="size-6 text-lime" />
          {k.title}
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-fg-3">{k.subtitle}</p>
      </header>

      {error && <p className="mb-4 rounded-2xl border border-danger/50 bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          {/* 1. Referencia */}
          <section className="space-y-3">
            <p className="px-1 text-[13px] font-semibold text-fg-2">{k.step1}</p>
            {!project && (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
                  {presets.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      disabled={!!busy}
                      onClick={() => analyze(p.video_url, p.name)}
                      className="group relative aspect-[3/4] overflow-hidden rounded-2xl border border-line bg-surface-3 text-left disabled:opacity-50"
                    >
                      <video src={p.video_url} poster={p.thumbnail_url || undefined} muted loop playsInline preload="none"
                        onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                        onMouseLeave={(e) => e.currentTarget.pause()}
                        className="absolute inset-0 size-full object-cover" />
                      <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2 text-xs font-semibold">{p.name}</span>
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  disabled={!!busy}
                  onClick={() => refInput.current?.click()}
                  className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-surface-4 text-[15px] font-semibold hover:bg-white/10 disabled:opacity-50"
                >
                  {busy === "analyze" ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
                  {busy === "analyze" ? k.analyzing : k.uploadRef}
                </button>
                <input ref={refInput} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
                  onChange={(e) => e.target.files?.[0] && uploadReference(e.target.files[0])} />
              </>
            )}
            {project && a && (
              <SettingCard label={`${k.analyzed} · ${project.title}`}>
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
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-fg-3">{k.sheets} ({a.sheets.length})</summary>
                  <div className="mt-2 grid gap-2">
                    {a.sheets.map((s) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={s.file} src={studio.katanaFile(project.id, "sheets", s.file)} alt={`${s.start}-${s.end}s`} className="w-full rounded-lg" loading="lazy" />
                    ))}
                  </div>
                </details>
                <button type="button" onClick={() => { setProject(null); setPlanned(null); }} className="mt-3 text-xs text-fg-3 underline">
                  {k.newRemix}
                </button>
              </SettingCard>
            )}
          </section>

          {/* 2. Sujeto y encargo */}
          {project && a && (
            <section className="space-y-3">
              <p className="px-1 text-[13px] font-semibold text-fg-2">{k.step2}</p>
              <SettingCard label={k.subjects}>
                <div className="flex flex-wrap gap-2">
                  {subjects.map((u) => (
                    <div key={u} className="relative size-20 overflow-hidden rounded-xl">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={u} alt="" className="size-full object-cover" />
                      <button type="button" onClick={() => setSubjects((s) => s.filter((x) => x !== u))}
                        className="absolute right-1 top-1 rounded-full bg-black/70 p-0.5"><X className="size-3" /></button>
                    </div>
                  ))}
                  {subjects.length < 5 && (
                    <button type="button" onClick={() => photoInput.current?.click()} disabled={busy === "photo"}
                      className="flex size-20 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-line text-xs text-fg-3 hover:bg-white/5">
                      {busy === "photo" ? <Loader2 className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}
                      {k.addPhoto}
                    </button>
                  )}
                </div>
                <input ref={photoInput} type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden"
                  onChange={(e) => e.target.files && addPhotos(e.target.files)} />
              </SettingCard>
              <SettingCard label={k.brief}>
                <textarea value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000} rows={3}
                  placeholder={k.briefPlaceholder} className="w-full resize-y rounded-xl bg-surface-2 p-3 text-sm outline-none" />
              </SettingCard>
              <div className="grid gap-3 md:grid-cols-2">
                <SettingCard label={k.aspect}>
                  <div className="flex flex-wrap gap-1.5">
                    {ASPECTS.map((x) => (
                      <Chip key={x} active={(aspect ?? a.aspect) === x} onClick={() => setAspect(x)}>{x}</Chip>
                    ))}
                  </div>
                </SettingCard>
                <SettingCard label={k.duration}>
                  <input type="number" min={3} max={60} step={0.5} value={duration ?? Math.min(30, Math.max(5, Math.round(a.energy.duration * 10) / 10))}
                    onChange={(e) => setDuration(Number(e.target.value) || null)} className="h-8 w-24 rounded-lg bg-surface-2 px-2 text-sm" />
                </SettingCard>
                <SettingCard label={k.resolution}>
                  <div className="flex gap-1.5">
                    {RESOLUTIONS.map((r) => <Chip key={r} active={resolution === r} onClick={() => setResolution(r)}>{r}</Chip>)}
                  </div>
                </SettingCard>
                <SettingCard label={`${k.maxClips} · ${k.maxSeconds}`}>
                  <div className="flex items-center gap-2">
                    <input type="number" min={1} max={6} value={maxClips} onChange={(e) => setMaxClips(Math.min(6, Math.max(1, Number(e.target.value) || 1)))}
                      className="h-8 w-16 rounded-lg bg-surface-2 px-2 text-sm" />
                    <input type="number" min={4} max={90} value={maxSeconds} onChange={(e) => setMaxSeconds(Math.min(90, Math.max(4, Number(e.target.value) || 4)))}
                      className="h-8 w-20 rounded-lg bg-surface-2 px-2 text-sm" />
                  </div>
                </SettingCard>
                <SettingCard label={k.music}>
                  <div className="flex gap-1.5">
                    <Chip active={music === "reference"} onClick={() => setMusic("reference")}>{k.musicRef}</Chip>
                    <Chip active={music === "none"} onClick={() => setMusic("none")}>{k.musicNone}</Chip>
                  </div>
                </SettingCard>
                <SettingCard label={k.language}>
                  <div className="flex gap-1.5">
                    {LANGUAGES.map((l) => <Chip key={l} active={language === l} onClick={() => setLanguage(l)}>{l}</Chip>)}
                  </div>
                </SettingCard>
              </div>

              {!quote ? (
                <button type="button" onClick={estimate} disabled={!!busy || !subjects.length}
                  className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-surface-4 text-[15px] font-semibold hover:bg-white/10 disabled:opacity-50">
                  {busy === "estimate" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4 text-lime" />}
                  {k.estimate}
                </button>
              ) : (
                <div className="space-y-2 rounded-2xl border border-lime/40 bg-lime/5 p-4">
                  {!quote.available ? (
                    <p className="text-sm text-danger">{k.noClaude}</p>
                  ) : (
                    <>
                      <p className="text-sm">{k.planCost(formatUsd(quote.max_usd))}</p>
                      <button type="button" onClick={plan} disabled={!!busy}
                        className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-lime text-[15px] font-semibold text-black disabled:opacity-60">
                        {busy === "plan" ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                        {busy === "plan" ? k.planning : k.approvePlan}
                      </button>
                    </>
                  )}
                </div>
              )}
            </section>
          )}

          {/* 3. Plan */}
          {project?.plan && (
            <section className="space-y-3">
              <p className="px-1 text-[13px] font-semibold text-fg-2">{k.step3}</p>
              <SettingCard label={project.plan.title}>
                <dl className="space-y-2 text-sm">
                  <div><dt className="text-xs text-fg-3">{k.trick}</dt><dd>{project.plan.trick}</dd></div>
                  <div><dt className="text-xs text-fg-3">{k.concept}</dt><dd>{project.plan.concept}</dd></div>
                  <div><dt className="text-xs text-fg-3">{k.look}</dt><dd>{project.plan.look} · {project.plan.aspect} · {project.plan.duration} s</dd></div>
                  {!!project.plan.locations.length && (
                    <div><dt className="text-xs text-fg-3">{k.locations}</dt>
                      {project.plan.locations.map((l) => <dd key={l.id} className="line-clamp-2"><b>{l.id}</b> {l.prompt}</dd>)}</div>
                  )}
                  {!!project.plan.stills.length && (
                    <div><dt className="text-xs text-fg-3">{k.stills}</dt>
                      {project.plan.stills.map((s) => <dd key={s.id} className="line-clamp-2"><b>{s.id}</b> {s.prompt}</dd>)}</div>
                  )}
                  <div><dt className="text-xs text-fg-3">{k.clips}</dt>
                    {project.plan.clips.map((c) => (
                      <dd key={c.id} className="line-clamp-3"><b>{c.id}</b> ({c.duration} s) {c.prompt}</dd>
                    ))}</div>
                  {project.plan.notes && <div><dt className="text-xs text-fg-3">{k.notes}</dt><dd>{project.plan.notes}</dd></div>}
                </dl>
                {planned && (
                  <p className="mt-3 text-xs text-fg-3">
                    {k.spent(formatUsd(planned.cost_usd))} · {k.generatedSeconds(planned.generated_seconds)}
                    {planned.warnings.map((w) => <span key={w} className="block text-warning">{w}</span>)}
                  </p>
                )}
              </SettingCard>
              {project.space_id && (
                <>
                  <Link href={`/spaces/${project.space_id}`}
                    className="flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-lime text-[15px] font-semibold text-black">
                    <Film className="size-4" />
                    {k.openSpace}
                    <ArrowRight className="size-4" />
                  </Link>
                  <p className="px-1 text-xs text-fg-3">{k.spaceHint}</p>
                </>
              )}
            </section>
          )}
        </div>

        <aside className="space-y-2">
          <p className="px-1 text-[13px] font-semibold text-fg-2">{k.previous}</p>
          {!projects.length && <p className="text-sm text-fg-3">{k.empty}</p>}
          {projects.map((p) => (
            <div key={p.id} className={clsx("flex items-center gap-2 rounded-xl border px-3 py-2",
              project?.id === p.id ? "border-lime/50 bg-lime/5" : "border-line bg-surface-3")}>
              <button type="button" onClick={() => open(p.id)} className="min-w-0 flex-1 text-left">
                <p className="truncate text-sm font-semibold">{p.title}</p>
                <p className="text-xs text-fg-3">{new Date(p.updated_at).toLocaleDateString()}{p.planned ? " · plan" : ""}</p>
              </button>
              <button type="button" onClick={() => remove(p.id)} title={k.remove} className="text-fg-3 hover:text-danger">
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
