"use client";

import { ArrowLeft, Code2, Folder, Loader2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Chip, SettingCard } from "@/components/studio/controls";
import { CostPanel, costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { MediaSlot } from "@/components/studio/media-slot";
import { localizePreset, presetOption } from "@/lib/i18n/presets";
import { probeDuration } from "@/lib/media";
import { costShort, studio, StudioError, type Estimate } from "@/lib/studio";
import type { Preset } from "@/lib/types";

const FALLBACK = { video: "/art/text-to-video.webp", image: "/art/text-to-image.webp" };

/** Formulario de un preset: variables → vista previa con costo → Generate. */
export function PresetRunner({ slug }: { slug: string }) {
  const { t, locale } = useI18n();
  const router = useRouter();
  const [raw, setPreset] = useState<Preset | null>(null);
  const preset = raw && localizePreset(raw, locale);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ key: string; input: Record<string, unknown>; estimate: Estimate | null; error?: string } | null>(null);
  const [videoSecs, setVideoSecs] = useState<Record<string, number>>({});
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showInput, setShowInput] = useState(false);
  const idempotency = useRef<string | null>(null);
  const { items, add, remove } = useGenerations();

  useEffect(() => {
    studio
      .preset(slug)
      .then((p) => {
        setPreset(p);
        setValues(Object.fromEntries(p.variables.filter((v) => v.default !== undefined).map((v) => [v.key, v.default])));
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [slug]);

  const videoUrls = (preset?.variables ?? [])
    .filter((v) => v.type === "video")
    .map((v) => values[v.key])
    .filter((u): u is string => typeof u === "string");
  const videoKey = videoUrls.join("|");
  useEffect(() => {
    for (const url of videoKey ? videoKey.split("|") : []) {
      probeDuration(url).then((s) => s && setVideoSecs((prev) => (prev[url] ? prev : { ...prev, [url]: s })));
    }
  }, [videoKey]);
  const hints: Record<string, number> =
    videoUrls.length && videoUrls.every((u) => videoSecs[u])
      ? { input_video_seconds: videoUrls.reduce((a, u) => a + videoSecs[u], 0) }
      : {};
  const hintsKey = JSON.stringify(hints);
  const valuesKey = JSON.stringify(values);
  const previewKey = `${valuesKey}|${hintsKey}`;
  const current = preview?.key === previewKey ? preview : null;

  useEffect(() => {
    if (!raw) return;
    const timer = setTimeout(() => {
      studio
        .previewPreset(raw.slug, JSON.parse(valuesKey), JSON.parse(hintsKey))
        .then((r) => setPreview({ key: previewKey, input: r.input, estimate: r.estimate }))
        .catch((e) => setPreview({ key: previewKey, input: {}, estimate: null, error: e.message }));
    }, 450);
    return () => clearTimeout(timer);
  }, [raw, previewKey, valuesKey, hintsKey]);

  function set(key: string, v: unknown) {
    idempotency.current = null;
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)));
  }

  async function submit() {
    if (!preset || submitting) return;
    if (!costAllowsDirectSubmit(current?.estimate ?? null) && confirmKey !== previewKey) {
      setConfirmKey(previewKey);
      return;
    }
    setConfirmKey(null);
    setSubmitting(true);
    setFormError(null);
    idempotency.current ??= crypto.randomUUID();
    try {
      add(await studio.runPreset(preset.slug, values, idempotency.current));
      idempotency.current = null;
    } catch (e) {
      if (e instanceof StudioError && e.details) {
        setErrors(Object.fromEntries(e.details.map((d) => [d.path.split("/")[0], d.message])));
      }
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) return <p className="m-8 rounded-2xl bg-danger/10 p-4 text-danger">{loadError}</p>;
  if (!preset) return <div className="shimmer m-3 h-[80vh] rounded-panel" />;

  const history = items.filter((g) => g.model === preset.model);
  const short = costShort(current?.estimate ?? null);
  const confirming = confirmKey === previewKey;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <div className="flex items-center gap-3 px-6 pt-5 pb-3">
          <Link href="/presets" className="text-fg-3 hover:text-fg" aria-label={t.presets.back}>
            <ArrowLeft className="size-5" />
          </Link>
          <span className="font-mono text-[15px] text-fg-2">/{preset.slug}</span>
          {!preset.builtin && (
            <button
              type="button"
              onClick={async () => {
                await studio.deletePreset(preset.slug);
                router.push("/presets");
              }}
              className="ml-auto text-fg-3 hover:text-danger"
              aria-label={t.presets.deletePreset}
              title={t.presets.deletePreset}
            >
              <Trash2 className="size-4" />
            </button>
          )}
        </div>
        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 pb-3">
          <div className="grain relative h-[196px] shrink-0 overflow-hidden rounded-2xl bg-surface-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={preset.cover ?? FALLBACK[preset.output]} alt="" className="absolute inset-0 size-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
            <div className="absolute right-4 bottom-4 left-4">
              <p className="headline text-[28px] text-lime drop-shadow">{preset.title}</p>
              <p className="mt-1 text-[15px] font-medium text-white/85">{preset.description}</p>
            </div>
          </div>

          {preset.variables.map((v) => {
            const err = errors[v.key];
            if (v.type === "image" || v.type === "images" || v.type === "video") {
              return (
                <MediaSlot
                  key={v.key}
                  label={v.label}
                  hint={v.placeholder ?? (v.type === "video" ? t.presets.videoHint : t.presets.imageHint)}
                  kind={v.type === "video" ? "video" : "image"}
                  multiple={v.type === "images"}
                  max={v.type === "images" ? 8 : 1}
                  required={!!v.required}
                  value={values[v.key] as string | string[] | undefined}
                  onChange={(val) => set(v.key, val)}
                  error={err}
                />
              );
            }
            if (v.type === "select") {
              return (
                <SettingCard key={v.key} label={v.label} error={err}>
                  <div className="flex flex-wrap gap-1.5">
                    {(v.options ?? []).map((o) => (
                      <Chip key={o} active={values[v.key] === o} onClick={() => set(v.key, o)}>
                        {presetOption(o, locale)}
                      </Chip>
                    ))}
                  </div>
                </SettingCard>
              );
            }
            return (
              <SettingCard key={v.key} label={v.label + (v.required ? "" : t.presets.optional)} error={err}>
                <textarea
                  value={(values[v.key] as string) ?? ""}
                  onChange={(e) => set(v.key, e.target.value || undefined)}
                  rows={v.type === "textarea" ? 4 : 2}
                  placeholder={v.placeholder}
                  className="w-full resize-none bg-transparent text-[16px] leading-relaxed outline-none placeholder:text-fg-4"
                />
              </SettingCard>
            );
          })}

          <button
            type="button"
            onClick={() => setShowInput((s) => !s)}
            className="flex items-center gap-2 px-1 text-xs text-fg-3 hover:text-fg-2"
          >
            <Code2 className="size-3.5" /> {t.presets.showInput(showInput, preset.model)}
          </button>
          {showInput && current && (
            <pre className="thin-scrollbar overflow-x-auto rounded-2xl border border-line bg-surface-2 p-3 font-mono text-[11px] text-fg-2">
              {JSON.stringify(current.input, null, 2)}
            </pre>
          )}
        </div>
        <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          <CostPanel loading={!current} estimate={current?.estimate ?? null} error={current?.error} needsConfirm={confirming} />
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="flex h-16 w-full items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] hover:brightness-105 active:translate-y-px disabled:opacity-50"
          >
            {submitting ? <Loader2 className="size-6 animate-spin" /> : confirming ? t.studio.generateAnyway : t.studio.generate}
            {!submitting && !confirming && short && <span className="text-[19px]">{short}</span>}
          </button>
        </div>
      </aside>

      <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col rounded-panel border border-line bg-surface-1">
        <div className="flex items-center gap-2 px-5 pt-4 pb-3">
          <span className="flex h-10 items-center gap-2 rounded-xl bg-surface-4 px-3 text-[15px] font-medium">
            <Folder className="size-4" /> {t.presets.history}
          </span>
          <span className="text-sm text-fg-3">{t.presets.generationsWith(preset.model)}</span>
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-5 pb-5">
          {history.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center py-20 text-center">
              <p className="headline text-[40px]">{preset.title}</p>
              <p className="mt-3 max-w-md text-fg-3">{preset.description}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="grid" onDelete={remove} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
