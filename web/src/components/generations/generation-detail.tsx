"use client";

import { ArrowLeft, Check, Copy, Download, Loader2, Mic, RotateCcw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CopyBlock } from "@/components/copy-block";
import { IconButton, StatusPill, modelName, sourceLabel } from "@/components/generations/generation-card";
import { useI18n } from "@/components/i18n-provider";
import { outputSrc, studio, VOICE_MODEL } from "@/lib/studio";
import type { Generation, ModelSummary } from "@/lib/types";

// Mismo criterio que la API (pricing._media_kind): claves que llevan archivos de entrada.
function mediaKind(key: string): "image" | "video" | "audio" | null {
  if (!(key.endsWith("_url") || key.endsWith("_urls") || key === "input_images")) return null;
  if (key.startsWith("video")) return "video";
  if (key.startsWith("audio")) return "audio";
  return "image";
}

const TEXT_KEYS = new Set(["prompt", "negative_prompt"]);

export function GenerationDetail({ id }: { id: string }) {
  const { t, locale } = useI18n();
  const d = t.history.detail;
  const router = useRouter();
  const [g, setG] = useState<Generation | null>(null);
  const [missing, setMissing] = useState(false);
  const [models, setModels] = useState<Map<string, ModelSummary>>(new Map());

  useEffect(() => {
    studio.models().then((r) => setModels(new Map(r.models.map((m) => [m.id, m])))).catch(() => undefined);
  }, []);

  // Carga y, mientras no termine, sigue el progreso con long-poll.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        let cur = await studio.get(id);
        if (alive) setG(cur);
        while (alive && !cur.terminal) {
          cur = await studio.get(id, 20);
          if (alive) setG(cur);
        }
      } catch {
        if (alive) setMissing(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  if (missing) {
    return (
      <div className="px-4 py-8 md:px-8">
        <BackLink label={d.back} />
        <p className="mt-16 text-center text-fg-3">{d.notFound}</p>
      </div>
    );
  }
  if (!g) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="size-6 animate-spin text-lime" />
      </div>
    );
  }

  const prompt = typeof g.input.prompt === "string" ? g.input.prompt : "";
  const negative = typeof g.input.negative_prompt === "string" ? g.input.negative_prompt : "";
  const entries = Object.entries(g.input);
  const media = entries.filter(([k]) => mediaKind(k));
  const params = entries.filter(([k]) => !mediaKind(k) && !TEXT_KEYS.has(k));
  const output = models.get(g.model)?.output;
  const fieldLabel = (k: string) => t.controls.fields[k] ?? t.media.labels[k]?.[0] ?? k;
  const show = (v: unknown) =>
    typeof v === "boolean" ? (v ? t.controls.on : t.controls.off) : typeof v === "object" ? JSON.stringify(v) : String(v);
  const took = Math.round(g.elapsed_seconds);

  return (
    <div className="px-4 py-8 md:px-8">
      <BackLink label={d.back} />
      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section className="flex min-w-0 flex-col gap-4">
          {g.status === "completed" && g.outputs.length > 0 ? (
            g.outputs.map((o, i) =>
              o.kind === "video" ? (
                <video key={i} src={outputSrc(o)} className="max-h-[80vh] w-full rounded-2xl bg-surface-3 object-contain" controls loop playsInline />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={i} src={outputSrc(o)} alt={prompt} className="max-h-[80vh] w-full rounded-2xl bg-surface-3 object-contain" />
              ),
            )
          ) : (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 rounded-2xl bg-surface-3 p-6 text-center">
              {!g.terminal && <Loader2 className="size-6 animate-spin text-lime" />}
              <StatusPill g={g} />
              {g.error && <p className="max-w-md text-sm text-fg-3">{g.error}</p>}
            </div>
          )}
          {g.outputs.length > 1 && <p className="text-sm text-fg-3">{d.outputs(g.outputs.length)}</p>}
        </section>

        <aside className="flex min-w-0 flex-col gap-5">
          <div className="flex items-center justify-between gap-2">
            <StatusPill g={g} />
            <div className="flex items-center gap-1">
              {g.status === "completed" && g.outputs[0] && (
                <IconButton label={t.generation.download} href={outputSrc(g.outputs[0])}>
                  <Download className="size-4" />
                </IconButton>
              )}
              {g.status === "completed" && g.outputs.some((o) => o.kind === "video") && (
                <IconButton label={t.voice.open} onClick={() => router.push(`/voice?from=${g.id}`)}>
                  <Mic className="size-4" />
                </IconButton>
              )}
              <IconButton
                label={t.generation.reuse}
                onClick={() =>
                  router.push(
                    g.model === VOICE_MODEL ? `/voice?reuse=${g.id}` : `/${output === "image" ? "image" : "video"}?reuse=${g.id}`,
                  )
                }
              >
                <RotateCcw className="size-4" />
              </IconButton>
              {g.terminal && (
                <IconButton
                  label={t.generation.delete}
                  onClick={async () => {
                    if (!window.confirm(d.deleteConfirm)) return;
                    await studio.remove(g.id);
                    router.push("/history");
                  }}
                >
                  <Trash2 className="size-4" />
                </IconButton>
              )}
            </div>
          </div>

          <Block title={d.model}>
            <p className="font-semibold">{modelName(g.model, locale, models)}</p>
            <p className="mt-1 font-mono text-xs break-all text-fg-3">{g.model}</p>
          </Block>

          {(prompt || !negative) && (
            <Block title={d.prompt} copy={prompt || undefined}>
              <p className={prompt ? "leading-relaxed whitespace-pre-wrap" : "text-fg-3 italic"}>
                {prompt || t.generation.noPrompt}
              </p>
            </Block>
          )}
          {negative && (
            <Block title={fieldLabel("negative_prompt")} copy={negative}>
              <p className="leading-relaxed whitespace-pre-wrap">{negative}</p>
            </Block>
          )}

          {params.length > 0 && (
            <Block title={d.params}>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
                {params.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-fg-3">{fieldLabel(k)}</dt>
                    <dd className="font-medium break-words">
                      {k === "duration" && typeof v === "number" ? `${v}s` : show(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            </Block>
          )}

          {media.length > 0 && (
            <Block title={d.inputs}>
              <div className="flex flex-col gap-3">
                {media.map(([k, v]) => (
                  <div key={k}>
                    <p className="mb-1.5 text-sm text-fg-3">{fieldLabel(k)}</p>
                    <div className="flex flex-wrap gap-2">
                      {(Array.isArray(v) ? v : [v]).map((url, i) => (
                        <InputThumb key={i} url={String(url)} kind={mediaKind(k)!} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Block>
          )}

          <Block title={d.info}>
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
              {g.source && (
                <>
                  <dt className="text-fg-3">{d.source}</dt>
                  <dd>{sourceLabel(g.source, d.webUi)}</dd>
                </>
              )}
              {g.keep_source_audio && (
                <>
                  <dt className="text-fg-3">{d.sourceAudio}</dt>
                  <dd>{d.sourceAudioState[g.outputs.find((o) => o.audio)?.audio ?? "pending"] ?? d.sourceAudioState.pending}</dd>
                </>
              )}
              <dt className="text-fg-3">{d.created}</dt>
              <dd>{new Date(g.created_at).toLocaleString(locale)}</dd>
              {g.terminal && (
                <>
                  <dt className="text-fg-3">{d.took}</dt>
                  <dd>{took < 60 ? `${took}s` : `${Math.floor(took / 60)}m ${String(took % 60).padStart(2, "0")}s`}</dd>
                </>
              )}
              <dt className="text-fg-3">{d.generationId}</dt>
              <dd className="font-mono text-xs break-all">{g.id}</dd>
              {g.request_id && (
                <>
                  <dt className="text-fg-3">{d.requestId}</dt>
                  <dd className="font-mono text-xs break-all">{g.request_id}</dd>
                </>
              )}
              {g.error && (
                <>
                  <dt className="text-fg-3">{d.error}</dt>
                  <dd className="text-danger">{g.error}</dd>
                </>
              )}
            </dl>
          </Block>

          <CopyBlock title={d.raw} code={JSON.stringify({ model: g.model, input: g.input }, null, 2)} />
        </aside>
      </div>
    </div>
  );
}

function BackLink({ label }: { label: string }) {
  return (
    <Link href="/history" className="inline-flex items-center gap-1.5 text-sm text-fg-3 hover:text-fg">
      <ArrowLeft className="size-4" /> {label}
    </Link>
  );
}

function Block({ title, copy, children }: { title: string; copy?: string; children: React.ReactNode }) {
  const [done, setDone] = useState(false);
  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold tracking-wide text-fg-3 uppercase">{title}</p>
        {copy && (
          <button
            type="button"
            aria-label={title}
            onClick={() => {
              navigator.clipboard.writeText(copy);
              setDone(true);
              setTimeout(() => setDone(false), 1500);
            }}
            className="rounded-md p-1 text-fg-3 hover:text-fg"
          >
            {done ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function InputThumb({ url, kind }: { url: string; kind: "image" | "video" | "audio" }) {
  const cls = "h-28 max-w-full rounded-xl bg-surface-3 object-cover";
  return (
    <a href={url} target="_blank" rel="noreferrer" title={url}>
      {kind === "video" ? (
        <video src={url} className={cls} muted playsInline preload="metadata" />
      ) : kind === "audio" ? (
        <audio src={url} controls className="max-w-full" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className={cls} loading="lazy" />
      )}
    </a>
  );
}
