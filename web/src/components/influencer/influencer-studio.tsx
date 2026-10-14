"use client";

import clsx from "clsx";
import { ChevronDown, Compass, Dices, History, Loader2, Mars, Minus, Plus, Sparkles, Venus, VenusAndMars } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { GenerationCard } from "@/components/generations/generation-card";
import { useGenerations } from "@/components/generations/use-generations";
import { useI18n } from "@/components/i18n-provider";
import { Chip, SettingCard } from "@/components/studio/controls";
import { CostPanel, costAllowsDirectSubmit } from "@/components/studio/cost-panel";
import { MediaSlot } from "@/components/studio/media-slot";
import { l } from "@/lib/i18n";
import { ANIMALS, CDN, EXAMPLES, GROUPS, TIERS, buildPrompt, randomSelection, type Example, type Selection, type Tier } from "@/lib/influencer-data";
import { costShort, fieldErrors, studio, StudioError, type Estimate } from "@/lib/studio";
import type { ModelDetail } from "@/lib/types";

/** Modelos para crear el personaje; `photo` es el que se usa si subes una foto (null = no acepta foto). */
const CREATE_MODELS = [
  { id: "higgsfield-ai/soul/v2/standard", photo: null, name: "Soul 2.0" },
  { id: "higgsfield-ai/soul/cinema", photo: null, name: "Soul Cinema" },
  { id: "marketing-studio/image/sunburst", photo: "marketing-studio/image/sunburst", name: "Sunburst" },
  { id: "marketing-studio/image/flare", photo: "marketing-studio/image/flare", name: "Flare" },
  { id: "xai/grok-imagine-image-2.0", photo: "xai/grok-imagine-image-2.0", name: "Grok Imagine 2.0" },
  { id: "alibaba/qwen-image-3/text-to-image", photo: "alibaba/qwen-image-3/edit", name: "Qwen Image 3" },
  { id: "z-image/turbo", photo: null, name: "Z-Image" },
  { id: "recraft/v4.1/pro/text-to-image", photo: null, name: "Recraft V4.1 Pro" },
  { id: "ideogram/v4.0", photo: null, name: "Ideogram 4.0" },
];
/** Modelos para el movimiento: los de referencias usan la hoja del personaje como referencia, el resto la anima. */
const MOTION_MODELS = [
  { id: "bytedance/seedance-2.0/reference-to-video", name: "Seedance 2.0 · Ref" },
  { id: "bytedance/seedance-2.5/reference-to-video", name: "Seedance 2.5 · Ref" },
  { id: "alibaba/wan-3.0/reference-to-video", name: "Wan 3.0 · Ref" },
  { id: "bytedance/seedance-2.0/image-to-video", name: "Seedance 2.0" },
  { id: "kling-video/v3.0/pro/image-to-video", name: "Kling 3.0 Pro" },
  { id: "minimax/hailuo-2.3/standard/image-to-video", name: "Hailuo 2.3" },
  { id: "alibaba/happy-horse/v1.1/image-to-video", name: "HappyHorse 1.1" },
];
const MOTIONS = [
  l("Camina hacia la cámara", "Walks confidently toward the camera"),
  l("Giro de pasarela", "Does a runway catwalk turn"),
  l("Baila un ritmo de moda", "Dances to an upbeat trending beat"),
  l("Habla a cámara como en un vlog", "Talks to the camera like a vlog"),
  l("Pelo al viento en cámara lenta", "Slow-motion hair flip and smile"),
  l("Salta y cae en pose", "Jumps and lands in a power pose"),
  l("Saluda y guiña un ojo", "Waves at the camera and winks"),
  l("Se pone unas gafas de sol", "Puts on sunglasses with attitude"),
];
const T = {
  kicker: l("Crea tu propio personaje con", "Create your own character with"),
  create: l("Crear influencer", "Create Influencer"),
  motion: l("Movimiento", "Motion"),
  photo: l("Sube tu foto", "Upload your photo"),
  photoHint: l("Opcional · usa tu cara como referencia", "Optional · use your face as reference"),
  model: l("Modelo", "Model"),
  noPhoto: l("no admite foto", "no photo"),
  type: l("Tipo de personaje", "Character type"),
  brief: l("Descripción extra", "Extra description"),
  briefHint: l("Ropa, rasgo estrella, actitud… (en inglés funciona mejor)", "Outfit, signature feature, attitude… (English works best)"),
  picked: l("Ajustes elegidos", "Picked settings"),
  reset: l("Quitar todo", "Reset all"),
  batch: l("Cantidad", "Batch size"),
  generate: l("Generar", "Generate"),
  anyway: l("Generar igual", "Generate anyway"),
  random: l("Al azar", "Randomize"),
  explore: l("Explorar", "Explore"),
  history: l("Historial", "History"),
  heroTitle1: l("Tu influencer,", "Your influencer,"),
  heroTitle2: l("tu hit viral", "your viral hit"),
  heroBody: l(
    "Crea tu AI influencer con la cara, el cuerpo y el estilo que quieras. Elige un movimiento y míralo actuar en un video listo para compartir.",
    "Build your AI influencer with the face, body, and style you want. Choose a motion and watch them perform it in a video ready to share.",
  ),
  examples: l("AI Influencers", "AI Influencers"),
  examplesNote: l("Ejemplos de la galería de Higgsfield", "Examples from Higgsfield's gallery"),
  recreate: l("Recrear", "Recreate"),
  character: l("Tu personaje", "Your character"),
  characterHint: l("La hoja del personaje o un retrato tuyo", "The character sheet or a portrait"),
  motionLabel: l("Movimiento", "Motion"),
  motionExtra: l("Detalles de la escena", "Scene details"),
  motionExtraHint: l("Lugar, ropa, música…", "Location, outfit, music…"),
  emptyHistory: l("Aún no has creado ningún influencer.", "You haven't created any influencer yet."),
};

/** Marca en el prompt para reconocer en el historial lo creado desde aquí. */
const MOTION_TAG = "same character, same face and outfit";

function GenderIcon({ id }: { id: string }) {
  const Icon = id === "female" ? Venus : id === "male" ? Mars : VenusAndMars;
  return <Icon className="size-4" />;
}

/** Ajusta la entrada al esquema de cada modelo: así funciona igual con cualquiera de la lista. */
function buildInput(detail: ModelDetail, base: { prompt: string; image?: string; ratio: string; seed?: number; batch?: number; motion?: boolean }) {
  const props = (detail.input_schema.properties ?? {}) as Record<string, { enum?: (string | number)[]; default?: unknown }>;
  const required = (detail.input_schema.required ?? []) as string[];
  const input: Record<string, unknown> = { prompt: base.prompt };
  const ratios = props.aspect_ratio?.enum?.map(String);
  if (ratios) {
    const prefer = base.motion ? ["9:16", "adaptive", "auto"] : [base.ratio];
    const r = prefer.find((x) => ratios.includes(x));
    if (r) input.aspect_ratio = r;
  }
  const res = props.resolution?.enum?.map(String);
  if (res) {
    const r = (base.motion ? ["720p", "768p"] : ["1080p", "2k", "2K"]).find((x) => res.includes(x));
    if (r) input.resolution = r;
  }
  if (props.seed && base.seed) input.seed = base.seed;
  if (props.batch_size && base.batch) input.batch_size = base.batch;
  if (base.image) {
    if (props.image_urls) input.image_urls = [base.image];
    else if (props.image_url) input.image_url = base.image;
  }
  for (const key of required) {
    if (input[key] === undefined && props[key]?.enum?.length && props[key].default === undefined) input[key] = props[key].enum![0];
  }
  return input;
}

export function InfluencerStudio({ initialTab }: { initialTab: "create" | "motion" }) {
  const { pick, t } = useI18n();
  const [tab, setTab] = useState(initialTab);
  const [view, setView] = useState<"explore" | "history">("explore");
  // Crear
  const [photo, setPhoto] = useState<string | undefined>();
  const [modelKey, setModelKey] = useState(CREATE_MODELS[0].id);
  const [tier, setTier] = useState<Tier>("normal");
  const [sel, setSel] = useState<Selection>({});
  const [brief, setBrief] = useState("");
  const [seed, setSeed] = useState<number | undefined>();
  const [batch, setBatch] = useState(1);
  const [open, setOpen] = useState<string | null>("type");
  // Movimiento
  const [character, setCharacter] = useState<string | undefined>();
  const [motion, setMotion] = useState(0);
  const [motionExtra, setMotionExtra] = useState("");
  const [motionModel, setMotionModel] = useState(MOTION_MODELS[0].id);
  // Cotización y envío
  const [details, setDetails] = useState<Record<string, ModelDetail>>({});
  const [quote, setQuote] = useState<{ key: string; value: Estimate | null; error?: string } | null>(null);
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const idempotency = useRef<string | null>(null);
  const { items, add, remove } = useGenerations();

  const createModel = CREATE_MODELS.find((m) => m.id === modelKey)!;
  const modelId = tab === "motion" ? motionModel : photo && createModel.photo ? createModel.photo : createModel.id;
  const detail = details[modelId];
  useEffect(() => {
    if (details[modelId]) return;
    studio.model(modelId).then((d) => setDetails((prev) => ({ ...prev, [modelId]: d })), () => undefined);
  }, [modelId, details]);

  const input = useMemo(() => {
    if (!detail) return null;
    if (tab === "motion") {
      if (!character) return null;
      const prompt = `The character ${MOTIONS[motion].en.toLowerCase()}, ${MOTION_TAG}${motionExtra.trim() ? `, ${motionExtra.trim()}` : ""}, smooth realistic motion, social media video`;
      return buildInput(detail, { prompt, image: character, ratio: "9:16", motion: true });
    }
    const usePhoto = !!photo && !!createModel.photo;
    return buildInput(detail, { prompt: buildPrompt(tier, sel, brief, usePhoto), image: usePhoto ? photo : undefined, ratio: "16:9", seed, batch });
  }, [detail, tab, character, motion, motionExtra, photo, createModel.photo, tier, sel, brief, seed, batch]);
  const quoteKey = input ? `${modelId}|${JSON.stringify(input)}` : null;
  const current = quote && quote.key === quoteKey ? quote : null;

  useEffect(() => {
    if (!quoteKey || !input) return;
    const timer = setTimeout(() => {
      studio
        .estimate(modelId, input)
        .then((value) => setQuote({ key: quoteKey, value }))
        .catch((e) => setQuote({ key: quoteKey, value: null, error: e instanceof Error ? e.message : String(e) }));
    }, 450);
    return () => clearTimeout(timer);
  }, [quoteKey, input, modelId]);

  function changeTier(next: Tier) {
    setTier(next);
    // Quita lo que el nuevo tipo no admite.
    setSel((prev) =>
      Object.fromEntries(
        Object.entries(prev)
          .map(([gid, ids]) => [gid, ids.filter((id) => GROUPS.find((x) => x.id === gid)?.options.find((o) => o.id === id)?.tiers.includes(next))])
          .filter(([, ids]) => ids.length),
      ),
    );
  }

  function toggle(gid: string, oid: string, max: number) {
    idempotency.current = null;
    setSel((prev) => {
      const cur = prev[gid] ?? [];
      const next = cur.includes(oid) ? cur.filter((x) => x !== oid) : max === 1 ? [oid] : [...cur, oid].slice(-max);
      const out = { ...prev, [gid]: next };
      if (!next.length) delete out[gid];
      return out;
    });
  }

  function recreate(ex: Example) {
    setTab("create");
    setTier(ex.tier);
    setSel(ex.sel);
    setBrief(ex.brief);
    setSeed(ex.seed);
    setOpen("type");
  }

  async function submit() {
    if (!input || submitting) return;
    if (!costAllowsDirectSubmit(current?.value ?? null) && confirmKey !== quoteKey) {
      setConfirmKey(quoteKey);
      return;
    }
    setConfirmKey(null);
    setSubmitting(true);
    setFormError(null);
    idempotency.current ??= crypto.randomUUID();
    try {
      const g = await studio.generate(
        modelId,
        input,
        idempotency.current,
        false,
        current?.value?.usd ?? null,
        {},
        current?.value?.reserve_usd ?? null,
        // Llegar aquí sin precio completo significa que el usuario confirmó un costo desconocido.
        !costAllowsDirectSubmit(current?.value ?? null),
      );
      add(g);
      setView("history");
      idempotency.current = null;
    } catch (e) {
      const fields = fieldErrors(e);
      setFormError(fields ? fields.map((f) => `${f.path}: ${f.message}`).join(" · ") : e instanceof Error ? e.message : String(e));
      if (e instanceof StudioError && e.status < 500) idempotency.current = null;
    } finally {
      setSubmitting(false);
    }
  }

  const picked = GROUPS.flatMap((grp) => (sel[grp.id] ?? []).map((id) => ({ grp, opt: grp.options.find((o) => o.id === id)! })));
  const history = items.filter((g) => {
    const p = String((g.input as Record<string, unknown>)?.prompt ?? "");
    return p.includes("Two-panel character sheet") || p.includes("Traits:") || p.includes(MOTION_TAG);
  });
  const short = costShort(current?.value ?? null);
  const confirming = confirmKey === quoteKey && !!quoteKey;
  const isAnimal = ANIMALS.includes(tier);

  const section = (id: string, title: string, count: number | null, body: React.ReactNode) => (
    <div className="rounded-2xl border border-line bg-surface-3">
      <button type="button" onClick={() => setOpen(open === id ? null : id)} className="flex w-full items-center gap-2 px-4 py-3 text-left text-[14px] text-fg-2">
        <span className="flex-1">
          {title}
          {count !== null && <span className="text-fg-4"> · {count}</span>}
        </span>
        <ChevronDown className={clsx("size-4 text-fg-3 transition-transform", open === id && "rotate-180")} />
      </button>
      {open === id && <div className="px-3 pb-3">{body}</div>}
    </div>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:h-[calc(100dvh-56px)] lg:flex-none lg:flex-row">
      <aside className="flex min-h-0 w-full shrink-0 flex-col rounded-panel border border-line bg-surface-1 lg:w-[470px]">
        <div className="px-5 pt-5 text-center">
          <p className="text-[12px] text-fg-3">{pick(T.kicker)}</p>
          <p className="headline text-[26px] uppercase">AI Influencer</p>
        </div>
        <div className="mx-3 mt-3 grid grid-cols-2 gap-1 rounded-2xl bg-surface-2 p-1">
          {(["create", "motion"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={clsx("rounded-xl py-2 text-sm font-semibold transition-colors", tab === k ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg")}
            >
              {pick(k === "create" ? T.create : T.motion)}
            </button>
          ))}
        </div>

        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
          {tab === "create" ? (
            <>
              <MediaSlot label={pick(T.photo)} hint={pick(T.photoHint)} kind="image" multiple={false} max={1} required={false} value={photo} onChange={(v) => setPhoto(v as string | undefined)} compact />
              <SettingCard label={pick(T.model)}>
                <div className="flex flex-wrap gap-1.5">
                  {CREATE_MODELS.map((m) => (
                    <Chip key={m.id} active={modelKey === m.id} onClick={() => setModelKey(m.id)}>
                      {m.name}
                      {photo && !m.photo && <span className="ml-1 font-normal text-fg-4">({pick(T.noPhoto)})</span>}
                    </Chip>
                  ))}
                </div>
              </SettingCard>
              {section(
                "type",
                pick(T.type),
                TIERS.length,
                <div className="grid grid-cols-3 gap-2">
                  {TIERS.map((x) => (
                    <button
                      key={x.id}
                      type="button"
                      onClick={() => changeTier(x.id)}
                      className={clsx(
                        "flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border-2 bg-white text-ink transition-colors",
                        tier === x.id ? "border-lime" : "border-transparent hover:border-line-2",
                      )}
                    >
                      {x.face ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={CDN + x.face} alt="" className="size-14 rounded-lg object-cover object-top" />
                      ) : (
                        <span className="text-[34px] leading-none">{x.emoji}</span>
                      )}
                      <span className="text-[12px] font-medium">{pick(x)}</span>
                    </button>
                  ))}
                </div>,
              )}
              {GROUPS.map((grp) => {
                const opts = grp.options.filter((o) => o.tiers.includes(tier));
                if (!opts.length) return null;
                return (
                  <div key={grp.id}>
                    {section(
                      grp.id,
                      pick(grp),
                      opts.length,
                      <div className="flex flex-wrap gap-1.5">
                        {opts.map((o) => (
                          <Chip key={o.id} active={(sel[grp.id] ?? []).includes(o.id)} onClick={() => toggle(grp.id, o.id, grp.max)}>
                            <span className="flex items-center gap-1">
                              {grp.id === "gender" && <GenderIcon id={o.id} />}
                              {pick(o)}
                            </span>
                          </Chip>
                        ))}
                      </div>,
                    )}
                  </div>
                );
              })}
              <SettingCard label={pick(T.brief)}>
                <textarea
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  rows={3}
                  placeholder={pick(T.briefHint)}
                  className="w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-fg-4"
                />
              </SettingCard>
              {(picked.length > 0 || isAnimal) && (
                <div className="px-1">
                  <div className="flex items-center justify-between text-[12px] text-fg-3">
                    <span>{pick(T.picked)}</span>
                    <button type="button" onClick={() => { setSel({}); setBrief(""); setSeed(undefined); }} className="hover:text-fg">
                      {pick(T.reset)}
                    </button>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    <span className="rounded-md bg-surface-4 px-2 py-1 text-[11px] text-fg-2">{pick(TIERS.find((x) => x.id === tier)!)}</span>
                    {picked.map(({ grp, opt }) => (
                      <button key={grp.id + opt.id} type="button" onClick={() => toggle(grp.id, opt.id, grp.max)} className="rounded-md bg-surface-4 px-2 py-1 text-[11px] text-fg-2 hover:text-danger">
                        {pick(opt)} ×
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {detail?.input_schema.properties?.batch_size && (
                <div className="flex items-center justify-between px-1 text-[14px]">
                  <span className="text-fg-2">{pick(T.batch)}</span>
                  <span className="flex items-center gap-3">
                    <button type="button" onClick={() => setBatch(1)} disabled={batch === 1} className="text-fg-3 hover:text-fg disabled:opacity-30" aria-label="−">
                      <Minus className="size-4" />
                    </button>
                    <span className="w-4 text-center font-semibold">{batch}</span>
                    <button type="button" onClick={() => setBatch(4)} disabled={batch === 4} className="text-fg-3 hover:text-fg disabled:opacity-30" aria-label="+">
                      <Plus className="size-4" />
                    </button>
                  </span>
                </div>
              )}
            </>
          ) : (
            <>
              <MediaSlot label={pick(T.character)} hint={pick(T.characterHint)} kind="image" multiple={false} max={1} required value={character} onChange={(v) => setCharacter(v as string | undefined)} />
              <SettingCard label={pick(T.motionLabel)}>
                <div className="flex flex-wrap gap-1.5">
                  {MOTIONS.map((m, i) => (
                    <Chip key={m.en} active={motion === i} onClick={() => setMotion(i)}>
                      {pick(m)}
                    </Chip>
                  ))}
                </div>
              </SettingCard>
              <SettingCard label={pick(T.motionExtra)}>
                <textarea
                  value={motionExtra}
                  onChange={(e) => setMotionExtra(e.target.value)}
                  rows={2}
                  placeholder={pick(T.motionExtraHint)}
                  className="w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-fg-4"
                />
              </SettingCard>
              <SettingCard label={pick(T.model)}>
                <div className="flex flex-wrap gap-1.5">
                  {MOTION_MODELS.map((m) => (
                    <Chip key={m.id} active={motionModel === m.id} onClick={() => setMotionModel(m.id)}>
                      {m.name}
                    </Chip>
                  ))}
                </div>
              </SettingCard>
            </>
          )}
        </div>

        <div className="sticky bottom-0 z-10 rounded-b-panel border-t border-line bg-surface-1 p-3">
          {formError && <p className="mb-2 px-1 text-sm text-danger">{formError}</p>}
          {input && <CostPanel loading={!current} estimate={current?.value ?? null} error={current?.error} needsConfirm={confirming} />}
          <div className="flex gap-2">
            {tab === "create" && (
              <button
                type="button"
                onClick={() => {
                  setSel(randomSelection(tier));
                  setSeed(undefined);
                }}
                className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-white text-ink hover:brightness-95"
                aria-label={pick(T.random)}
                title={pick(T.random)}
              >
                <Dices className="size-6" />
              </button>
            )}
            <button
              type="button"
              onClick={submit}
              disabled={submitting || !input}
              className="flex h-16 flex-1 items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-b from-[#e3ff4d] to-lime text-[21px] font-semibold text-ink shadow-[inset_0_-5px_0_rgba(80,100,0,0.35),0_10px_30px_-10px_rgba(209,254,23,0.45)] hover:brightness-105 active:translate-y-px disabled:opacity-50"
            >
              {submitting ? <Loader2 className="size-6 animate-spin" /> : pick(confirming ? T.anyway : T.generate)}
              {!submitting && !confirming && short && (
                <span className="flex items-center gap-1 text-[19px]">
                  <Sparkles className="size-4" />
                  {short}
                </span>
              )}
            </button>
          </div>
        </div>
      </aside>

      <section className="flex min-h-[60vh] min-w-0 flex-1 flex-col rounded-panel border border-line bg-surface-1">
        <div className="flex items-center gap-1 px-5 pt-4 pb-3">
          {(["explore", "history"] as const).map((v) => {
            const Icon = v === "explore" ? Compass : History;
            return (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={clsx("flex h-9 items-center gap-1.5 rounded-xl px-3 text-[14px] font-medium", view === v ? "bg-surface-4 text-fg" : "text-fg-3 hover:text-fg")}
              >
                <Icon className="size-4" /> {pick(v === "explore" ? T.explore : T.history)}
                {v === "history" && history.length > 0 && <span className="text-fg-4">{history.length}</span>}
              </button>
            );
          })}
        </div>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto px-5 pb-5">
          {view === "explore" ? (
            <>
              <div className="flex flex-col items-center py-6 text-center">
                <div className="flex items-end justify-center -space-x-6">
                  {[EXAMPLES[2], EXAMPLES[5], EXAMPLES[0], EXAMPLES[12], EXAMPLES[6]].map((ex, i) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={ex.id}
                      src={ex.thumb}
                      alt=""
                      className={clsx("rounded-xl object-cover shadow-2xl ring-1 ring-black/40", i === 2 ? "z-10 h-44 w-36" : i === 1 || i === 3 ? "h-36 w-28" : "h-28 w-24")}
                    />
                  ))}
                </div>
                <p className="headline mt-6 text-[34px] leading-[1.05] uppercase md:text-[44px]">
                  {pick(T.heroTitle1)}
                  <br />
                  {pick(T.heroTitle2)}
                </p>
                <p className="mt-3 max-w-xl text-[15px] text-fg-3">{pick(T.heroBody)}</p>
              </div>
              <div className="mb-3 flex items-center justify-between">
                <span className="rounded-xl bg-surface-4 px-3 py-1.5 text-[13px] font-medium">{pick(T.examples)}</span>
                <span className="text-[12px] text-fg-4">{pick(T.examplesNote)}</span>
              </div>
              <div className="columns-2 gap-3 xl:columns-3">
                {EXAMPLES.map((ex) => (
                  <button key={ex.id} type="button" onClick={() => recreate(ex)} className="group relative mb-3 block w-full overflow-hidden rounded-2xl bg-white">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={ex.thumb} alt="" loading="lazy" style={{ aspectRatio: `${ex.w} / ${ex.h}` }} className="w-full object-cover" />
                    <span className="absolute right-3 bottom-3 flex items-center gap-1 rounded-lg bg-lime px-2.5 py-1.5 text-[13px] font-semibold text-ink opacity-0 transition-opacity group-hover:opacity-100">
                      <Sparkles className="size-3.5" /> {pick(T.recreate)}
                    </span>
                  </button>
                ))}
              </div>
            </>
          ) : history.length === 0 ? (
            <p className="py-20 text-center text-fg-3">{pick(T.emptyHistory)}</p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {history.map((g) => (
                <GenerationCard key={g.id} g={g} layout="grid" onDelete={remove} />
              ))}
            </div>
          )}
        </div>
        <p className="px-5 pb-3 text-[11px] text-fg-4">
          {t.nav.models}: <Link href="/models" className="underline">{detail?.title ?? modelId}</Link>
        </p>
      </section>
    </div>
  );
}
