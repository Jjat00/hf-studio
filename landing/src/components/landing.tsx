"use client";

import clsx from "clsx";
import { ArrowRight, BookOpen, Check, Coins, Copy, Globe, Layers, Library, Play, Repeat, Shapes, ShieldCheck, Sparkles, Star, Terminal } from "lucide-react";
import { useState } from "react";
import { REPO, AUTHOR } from "@/lib/dict";
import { useI18n } from "./i18n";
import { Logo } from "./logo";
import { AudioPlayer, LoopVideo, SfxPad, VoiceCompare } from "./media";

const M = "/media";

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden className={className}>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function Kicker({ children }: { children: React.ReactNode }) {
  return <p className="text-[13px] font-semibold tracking-[0.14em] text-lime uppercase">{children}</p>;
}

function Nav() {
  const { t, locale, setLocale } = useI18n();
  const links = [
    ["#ejemplos", t.nav.examples],
    ["#spaces", t.nav.spaces],
    ["#proveedores", t.nav.providers],
    ["#audio", t.nav.audio],
    ["#agentes", t.nav.agents],
    ["#empezar", t.nav.start],
  ];
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-page/80 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4">
        <a href="#" className="flex items-center gap-2.5">
          <Logo size={30} />
          <span className="text-[17px] font-semibold tracking-[-0.01em]">HF Studio</span>
        </a>
        <div className="ml-4 hidden items-center md:flex">
          {links.map(([href, label]) => (
            <a key={href} href={href} className="rounded-lg px-2.5 py-1 text-sm font-medium text-fg-3 transition-colors hover:text-fg">
              {label}
            </a>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setLocale(locale === "es" ? "en" : "es")}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-fg-2 hover:bg-glass hover:text-fg"
            aria-label="Language"
          >
            <Globe className="size-4" /> {locale.toUpperCase()}
          </button>
          <a
            href={REPO}
            className="flex items-center gap-2 rounded-lg bg-lime px-3 py-1.5 text-sm font-semibold text-ink transition-colors hover:bg-lime-400"
          >
            <GitHubMark className="size-4" />
            <span className="hidden sm:inline">{t.nav.star}</span>
            <span className="sm:hidden">GitHub</span>
          </a>
        </div>
      </nav>
    </header>
  );
}

/** Barra de prompt como la del estudio, con el texto escribiéndose solo. */
function PromptBar() {
  const { t } = useI18n();
  return (
    <div className="mt-10 flex w-full max-w-[760px] items-stretch gap-2 text-left">
      <div className="flex min-w-0 flex-1 flex-col justify-between gap-3 rounded-2xl border border-white/10 bg-black/45 p-4 backdrop-blur-xl">
        <p className="truncate text-[15px] text-white/80">
          {t.hero.prompt}
          <span className="caret ml-0.5 text-lime">▍</span>
        </p>
        <div className="flex flex-wrap gap-1.5 text-[12px] font-semibold text-white/80">
          {[t.hero.model, "8s", "16:9"].map((c) => (
            <span key={c} className="rounded-lg bg-white/10 px-2 py-1">
              {c}
            </span>
          ))}
        </div>
      </div>
      <div className="flex w-[104px] shrink-0 flex-col items-center justify-center rounded-2xl bg-lime text-ink shadow-[inset_0_-3px_0_rgba(0,0,0,0.12)]">
        <span className="text-[13px] font-extrabold uppercase">{t.hero.generate}</span>
      </div>
    </div>
  );
}

function Hero() {
  const { t } = useI18n();
  return (
    <section className="px-4 pt-3">
      <div className="grain relative mx-auto flex min-h-[680px] max-w-[1400px] flex-col items-center justify-center overflow-hidden rounded-[28px] px-6 py-20 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/art/explore-hero.webp" alt="" className="absolute inset-0 size-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-black/30 to-black/80" />
        <div className="relative flex w-full flex-col items-center">
          <p className="rounded-full border border-white/15 bg-black/30 px-3.5 py-1.5 text-[13px] font-medium text-white/85 backdrop-blur">{t.hero.eyebrow}</p>
          <h1 className="headline mt-6 max-w-5xl text-[40px] leading-[1.08] sm:text-[56px] md:text-[76px]">
            {t.hero.title1}
            <br />
            <span className="text-lime">{t.hero.title2}</span>
          </h1>
          <p className="mt-6 max-w-2xl text-[17px] leading-relaxed text-white/85 md:text-[18px]">{t.hero.body}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <a
              href={REPO}
              className="flex items-center gap-2 rounded-xl bg-white px-6 py-3.5 text-[16px] font-semibold text-ink shadow-[inset_0_-3px_0_rgba(0,0,0,0.12)]"
            >
              <GitHubMark className="size-5" /> {t.hero.ctaRepo}
            </a>
            <a href="#promo" className="flex items-center gap-2 rounded-xl border border-white/20 bg-black/30 px-6 py-3.5 text-[16px] font-semibold backdrop-blur hover:bg-black/50">
              <Play className="size-4" fill="currentColor" /> {t.hero.ctaPromo}
            </a>
          </div>
          <PromptBar />
        </div>
      </div>
      <div className="mx-auto mt-4 grid max-w-[1400px] grid-cols-2 gap-3 md:grid-cols-4">
        {t.stats.map((s) => (
          <div key={s.label} className="rounded-[20px] border border-line bg-surface-2 px-5 py-5">
            <p className="headline text-[40px] leading-none text-lime">{s.value}</p>
            <p className="mt-2 text-[15px] text-fg-3">{s.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Promo() {
  const { t } = useI18n();
  return (
    <section id="promo" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="grid items-center gap-8 rounded-[28px] border border-line bg-surface-1 p-4 md:p-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <video src={`${M}/promo.mp4`} poster={`${M}/promo.jpg`} controls playsInline preload="none" className="aspect-video w-full rounded-[18px] bg-black" />
        <div className="px-2 pb-2 lg:pb-0">
          <h2 className="headline text-[32px] md:text-[40px]">{t.promo.title}</h2>
          <p className="mt-3 text-[17px] leading-relaxed text-fg-2">{t.promo.body}</p>
        </div>
      </div>
    </section>
  );
}

type Item = { type: "video" | "image"; src: string; tag: string; model: string; tall?: boolean };
const EXAMPLES: Item[] = [
  { type: "video", src: "soda-producto", model: "Kling O3", tag: "video-reference", tall: true },
  { type: "video", src: "tinta", model: "Wan 2.7", tag: "text-to-video" },
  { type: "image", src: "sneaker", model: "Soul V2", tag: "text-to-image" },
  { type: "video", src: "anime", model: "Seedance 2.5", tag: "video-edit" },
  { type: "video", src: "frappe-ugc", model: "Kling O3", tag: "first-last-frame", tall: true },
  { type: "image", src: "robot", model: "Soul V2", tag: "text-to-image" },
  { type: "video", src: "ciudad", model: "Wan 2.7", tag: "text-to-video" },
  { type: "video", src: "soda-ugc", model: "Wan 3.0", tag: "reference-to-video", tall: true },
  { type: "image", src: "lago", model: "Soul V2", tag: "text-to-image" },
];

function Examples() {
  const { t } = useI18n();
  return (
    <section id="ejemplos" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="mb-8 max-w-2xl">
        <Kicker>{t.examples.kicker}</Kicker>
        <h2 className="headline mt-2 text-[40px] md:text-[56px]">{t.examples.title}</h2>
        <p className="mt-3 text-[17px] text-fg-2">{t.examples.body}</p>
      </div>
      <div className="columns-1 gap-4 sm:columns-2 lg:columns-3">
        {EXAMPLES.map((e) => (
          <figure key={e.src} className="group relative mb-4 break-inside-avoid overflow-hidden rounded-[20px] bg-surface-3">
            {e.type === "video" ? (
              <LoopVideo src={`${M}/${e.src}.mp4`} poster={`${M}/${e.src}.jpg`} className={clsx("w-full object-cover", e.tall ? "aspect-[9/16]" : "aspect-video")} />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={`${M}/${e.src}.webp`} alt="" loading="lazy" className="aspect-square w-full object-cover" />
            )}
            <figcaption className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-gradient-to-t from-black/80 to-transparent p-3 pt-10">
              <span className="rounded-lg bg-black/50 px-2 py-1 text-[13px] font-semibold backdrop-blur">{e.model}</span>
              <span className="rounded-lg bg-lime/15 px-2 py-1 text-[12px] font-semibold text-lime backdrop-blur">{e.tag}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function Capabilities() {
  const { t } = useI18n();
  return (
    <section className="mx-auto w-full max-w-[1400px] px-4">
      <div className="mb-8 max-w-3xl">
        <h2 className="headline text-[36px] md:text-[48px]">{t.caps.title}</h2>
        <p className="mt-3 text-[17px] text-fg-2">{t.caps.body}</p>
      </div>
      <div className="grid grid-cols-1 gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
        {t.caps.items.map((c) => (
          <div key={c.art} className="group">
            <div className="grain relative aspect-[16/9] overflow-hidden rounded-[18px] bg-surface-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/art/${c.art}.webp`} alt="" loading="lazy" className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.03]" />
            </div>
            <p className="headline mt-4 text-[20px] tracking-[-0.03em]">{c.title}</p>
            <p className="mt-1 text-[16px] text-fg-3">{c.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Colores de los tipos de dato, los mismos que en el lienzo de la app.
const KIND = { text: "#60a5fa", image: "#a78bfa", video: "#4ade80", audio: "#fb923c" } as const;

/** Esquema de un lienzo de Spaces: un Assistant escribe escenas, una Lista las lleva en lote a imagen y video, y se
 *  combinan y se les mezcla música. Dibujado en SVG (sin capturas): ilustra el flujo, no es una generación real. */
function SpacesDiagram() {
  const { t } = useI18n();
  const d = t.spaces.diagram;
  const W = 170;
  const H = 64;
  // Solo cadenas que el producto ejecuta: la Lista es una entrada; su lote baja en pares (3 prompts → 3 imágenes →
  // 3 videos) y cada video se mezcla con la misma voz en off (revisión 69).
  const nodes = [
    { id: "list", x: 60, y: 30, kind: "text", label: d.list, sub: "prompts" },
    { id: "image", x: 420, y: 30, kind: "image", label: d.image, sub: "Nano Banana Pro" },
    { id: "video", x: 780, y: 30, kind: "video", label: d.video, sub: "Kling 3.0" },
    { id: "assistant", x: 60, y: 200, kind: "text", label: d.assistant, sub: d.script },
    { id: "voice", x: 420, y: 200, kind: "audio", label: d.voice, sub: "ElevenLabs" },
    { id: "mix", x: 780, y: 200, kind: "video", label: d.mix, sub: `×3 · ${d.free}` },
  ] as const;
  const at = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const right = (id: string) => [at[id].x + W, at[id].y + H / 2];
  const left = (id: string) => [at[id].x, at[id].y + H / 2];
  const bottom = (id: string) => [at[id].x + W / 2, at[id].y + H];
  const top = (id: string) => [at[id].x + W / 2, at[id].y];
  const curve = ([x1, y1]: number[], [x2, y2]: number[], vertical = false) =>
    vertical ? `M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}` : `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
  const edges = [
    { d: curve(right("list"), left("image")), kind: "text", batch: true },
    { d: curve(right("image"), left("video")), kind: "image", batch: true },
    { d: curve(bottom("video"), top("mix"), true), kind: "video", batch: true },
    { d: curve(right("assistant"), left("voice")), kind: "text", batch: false },
    { d: curve(right("voice"), left("mix")), kind: "audio", batch: false },
  ] as const;
  return (
    <div className="overflow-hidden rounded-[24px] border border-line bg-surface-2 p-3 sm:p-5">
      <svg viewBox="0 0 1010 300" className="w-full" role="img" aria-label={t.spaces.title}>
        <defs>
          <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.2" fill="rgba(255,255,255,0.08)" />
          </pattern>
        </defs>
        <rect width="1010" height="300" fill="url(#dots)" />
        {edges.map((e) => (
          <path key={e.d} d={e.d} fill="none" stroke={KIND[e.kind]} strokeWidth="2.5" strokeDasharray={e.batch ? "7 5" : undefined} />
        ))}
        {nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`}>
            <rect width={W} height={H} rx="14" fill="#1c1e21" stroke="rgba(255,255,255,0.14)" />
            <circle cx="18" cy="22" r="5" fill={KIND[n.kind]} />
            <text x="32" y="27" fill="#f7f7f8" fontSize="15" fontWeight="600">{n.label}</text>
            <text x="18" y="48" fill="rgba(255,255,255,0.45)" fontSize="13">{n.sub}</text>
          </g>
        ))}
        <text x="20" y="288" fill="#d1fe17" fontSize="14" fontWeight="600">{d.total}</text>
      </svg>
    </div>
  );
}

function Spaces() {
  const { t } = useI18n();
  const sp = t.spaces;
  return (
    <section id="spaces" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="mb-8 max-w-3xl">
        <Kicker>{sp.kicker}</Kicker>
        <h2 className="headline mt-3 text-[36px] md:text-[48px]">{sp.title}</h2>
        <p className="mt-3 text-[17px] text-fg-2">{sp.body}</p>
      </div>
      <SpacesDiagram />
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sp.points.map((pt) => (
          <div key={pt.title} className="flex flex-col rounded-[22px] border border-line bg-surface-2 p-5">
            <p className="text-[18px] font-semibold tracking-[-0.01em]">{pt.title}</p>
            <p className="mt-1.5 text-[15px] leading-snug text-fg-3">{pt.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Cotización real de HF Studio el 2026-10-03 (Seedance 2.0, 5 s, 720p).
const PRICES = [
  { name: "APIMart", usd: 0.71 },
  { name: "KIE", usd: 1.025 },
  { name: "Higgsfield", usd: 1.51 },
];

function Providers() {
  const { t, locale } = useI18n();
  const p = t.providers;
  const max = Math.max(...PRICES.map((x) => x.usd));
  const money = (usd: number) =>
    new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 3 }).format(usd);
  return (
    <section id="proveedores" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="mb-8 max-w-3xl">
        <Kicker>{p.kicker}</Kicker>
        <h2 className="headline mt-3 text-[36px] md:text-[48px]">{p.title}</h2>
        <p className="mt-3 text-[17px] text-fg-2">{p.body}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
        <div className="flex flex-col gap-5 rounded-[24px] border border-line bg-surface-2 p-6">
          <p className="text-[14px] font-medium text-fg-3">{p.example}</p>
          {PRICES.map((x, i) => (
            <div key={x.name}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[17px] font-semibold">
                  {x.name}
                  {i === 0 && <span className="ml-2 rounded-md bg-lime px-1.5 py-0.5 text-[11px] font-bold text-ink uppercase">{p.cheapest}</span>}
                </span>
                <span className="text-[17px] font-semibold tabular-nums">{money(x.usd)}</span>
              </div>
              <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface-3">
                <div className={clsx("h-full rounded-full", i === 0 ? "bg-lime" : "bg-fg-3/40")} style={{ width: `${(x.usd / max) * 100}%` }} />
              </div>
            </div>
          ))}
          <p className="mt-auto text-[15px] font-semibold text-lime">{p.saves}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {p.points.map((pt) => (
            <div key={pt.title} className="flex flex-col rounded-[22px] border border-line bg-surface-2 p-5">
              <p className="text-[18px] font-semibold tracking-[-0.01em]">{pt.title}</p>
              <p className="mt-1.5 text-[15px] leading-snug text-fg-3">{pt.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Card({ title, body, children, className }: { title: string; body: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={clsx("flex flex-col gap-4 rounded-[24px] border border-line bg-surface-2 p-6", className)}>
      <div>
        <p className="text-[20px] font-semibold tracking-[-0.01em]">{title}</p>
        <p className="mt-1 text-[15px] leading-snug text-fg-3">{body}</p>
      </div>
      {children}
    </div>
  );
}

function Audio() {
  const { t } = useI18n();
  const a = t.audio;
  const sfx = ["sfx-trueno", "sfx-murcielagos", "sfx-caja", "sfx-camara", "sfx-campana", "sfx-risa"];
  return (
    <section id="audio" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="mb-8 max-w-3xl">
        <Kicker>{a.kicker}</Kicker>
        <h2 className="headline mt-2 text-[40px] md:text-[56px]">{a.title}</h2>
        <p className="mt-3 text-[17px] text-fg-2">{a.body}</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <Card title={a.voiceChange.title} body={a.voiceChange.body}>
          <VoiceCompare before={`${M}/voz-antes.mp4`} after={`${M}/voz-despues.mp4`} labels={a.voiceChange} />
        </Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card title={a.tts.title} body={a.tts.body} className="sm:col-span-2">
            <p className="text-[15px] leading-relaxed text-fg-2 italic">{a.tts.quote}</p>
            <AudioPlayer src={`${M}/tts-promo.mp3`} label="eleven_v4" sub="ElevenLabs · text_to_speech" />
          </Card>
          <Card title={a.free.title} body={a.free.body}>
            <div className="mt-auto flex flex-col gap-2">
              <AudioPlayer src={`${M}/free-gonzalo.mp3`} label={a.free.voices[0]} sub="edge-tts" />
              <AudioPlayer src={`${M}/free-salome.mp3`} label={a.free.voices[1]} sub="edge-tts" />
            </div>
          </Card>
          <Card title={a.music.title} body={a.music.body}>
            <div className="mt-auto">
              <AudioPlayer src={`${M}/music-promo.mp3`} label="Tech launch · 118 BPM" sub="ElevenLabs · compose_music" />
            </div>
          </Card>
          <Card title={a.sfx.title} body={a.sfx.body} className="sm:col-span-2">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {sfx.map((s, i) => (
                <SfxPad key={s} src={`${M}/${s}.mp3`} label={a.sfx.items[i]} />
              ))}
            </div>
          </Card>
        </div>
      </div>
    </section>
  );
}

function CopyLine({ text }: { text: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        });
      }}
      className="flex items-center gap-1.5 rounded-lg bg-surface-5 px-2.5 py-1 text-[12px] font-semibold text-fg-2 hover:text-fg"
    >
      {done ? <Check className="size-3.5 text-lime" /> : <Copy className="size-3.5" />}
      {done ? t.start.copied : t.start.copy}
    </button>
  );
}

function Agents() {
  const { t } = useI18n();
  const g = t.agents;
  const connect = "uv run hf-studio connect claude-code";
  return (
    <section id="agentes" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <div className="grain relative min-h-[520px] overflow-hidden rounded-[28px] bg-surface-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/art/mcp.webp" alt="" className="absolute inset-0 size-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/50 to-black/20" />
          <div className="relative flex h-full flex-col justify-between gap-8 p-8 md:p-10">
            <div>
              <Kicker>{g.kicker}</Kicker>
              <p className="headline mt-3 text-[44px] leading-none md:text-[60px]">{g.title1}</p>
              <p className="headline text-[44px] leading-none text-lime md:text-[60px]">{g.title2}</p>
              <p className="mt-5 max-w-lg text-[17px] leading-relaxed text-white/85">{g.body}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {["Claude Code", "Codex", "Claude Desktop", "ChatGPT"].map((c) => (
                <span key={c} className="rounded-xl border border-white/15 bg-black/40 px-3 py-1.5 text-[14px] font-semibold backdrop-blur">
                  {c}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="flex flex-1 flex-col gap-3 rounded-[28px] border border-line bg-surface-1 p-5 font-mono text-[13.5px] leading-relaxed md:p-6">
            <div className="flex items-center gap-2 pb-2 text-fg-3">
              <Terminal className="size-4" /> <span className="font-sans text-[13px] font-semibold">claude</span>
            </div>
            <p className="self-end rounded-2xl rounded-br-md bg-surface-4 px-4 py-2.5 font-sans text-[15px]">{g.chat.user}</p>
            <div className="flex flex-col gap-1">
              {g.chat.tools.map((tool) => (
                <p key={tool} className="text-fg-3">
                  <span className="text-success">●</span> hf-studio · <span className="text-fg-2">{tool}</span>
                </p>
              ))}
            </div>
            <p className="max-w-[90%] rounded-2xl rounded-bl-md border border-lime/30 bg-lime/10 px-4 py-2.5 font-sans text-[15px] text-lime-300">{g.chat.quote}</p>
            <p className="self-end rounded-2xl rounded-br-md bg-surface-4 px-4 py-2.5 font-sans text-[15px]">{g.chat.ok}</p>
            <div className="flex flex-col gap-1">
              {["generate (quote_id)", "get_generation → terminal", "download_outputs"].map((tool) => (
                <p key={tool} className="text-fg-3">
                  <span className="text-success">●</span> hf-studio · <span className="text-fg-2">{tool}</span>
                </p>
              ))}
            </div>
            <p className="font-sans text-[15px] text-fg">✓ {g.chat.done}</p>
          </div>
          <div className="rounded-[22px] border border-line bg-surface-2 p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[15px] font-semibold">{g.connect}</p>
              <CopyLine text={connect} />
            </div>
            <pre className="thin-scrollbar mt-3 overflow-x-auto rounded-xl bg-surface-1 px-4 py-3 font-mono text-[14px] text-lime-300">$ {connect}</pre>
            <p className="mt-3 flex gap-2 text-[14px] leading-snug text-fg-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-lime" /> {g.rule}
            </p>
            <p className="mt-2 flex gap-2 text-[14px] leading-snug text-fg-3">
              <Terminal className="mt-0.5 size-4 shrink-0 text-lime" />
              <span>
                {g.forAgents.split(/(\{llms\}|\{agents\})/).map((part, i) =>
                  part === "{llms}" ? (
                    <a key={i} href="/llms.txt" className="font-mono text-fg-2 underline underline-offset-2 hover:text-lime">
                      llms.txt
                    </a>
                  ) : part === "{agents}" ? (
                    <a key={i} href={`${REPO}/blob/main/AGENTS.md`} className="font-mono text-fg-2 underline underline-offset-2 hover:text-lime">
                      AGENTS.md
                    </a>
                  ) : (
                    part
                  ),
                )}
              </span>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

const MORE_ICONS = { library: Library, coins: Coins, layers: Layers, sparkles: Sparkles, book: BookOpen, shield: ShieldCheck, shapes: Shapes, repeat: Repeat };

function More() {
  const { t } = useI18n();
  const shots = ["doc-estudio-video", "doc-modelos", "doc-casos-de-uso"];
  return (
    <section className="mx-auto w-full max-w-[1400px] px-4">
      <h2 className="headline mb-8 text-[36px] md:text-[48px]">{t.more.title}</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {t.more.items.map((m) => {
          const Icon = MORE_ICONS[m.icon as keyof typeof MORE_ICONS];
          return (
            <div key={m.title} className="flex min-h-[170px] flex-col rounded-[22px] border border-line bg-surface-2 p-5 transition-colors hover:border-line-2 hover:bg-surface-3">
              <Icon className="size-6" strokeWidth={2.2} />
              <div className="mt-auto pt-6">
                <p className="text-[19px] font-semibold tracking-[-0.01em]">{m.title}</p>
                <p className="mt-1.5 text-[15px] leading-snug text-fg-3">{m.desc}</p>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {shots.map((s, i) => (
          <figure key={s} className="overflow-hidden rounded-[20px] border border-line bg-surface-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${M}/${s}.webp`} alt={t.more.shots[i]} loading="lazy" className="aspect-[16/10] w-full object-cover object-top" />
            <figcaption className="px-4 py-3 text-[14px] font-medium text-fg-2">{t.more.shots[i]}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

function Start() {
  const { t } = useI18n();
  const cmd = "git clone https://github.com/Jjat00/hf-studio.git\ncd hf-studio\n./dev.sh        # macOS, Linux, WSL\n.\\dev           # Windows";
  return (
    <section id="empezar" className="mx-auto w-full max-w-[1400px] scroll-mt-20 px-4">
      <div className="grid gap-8 rounded-[28px] border border-line bg-surface-1 p-6 md:p-10 lg:grid-cols-2 [&>*]:min-w-0">
        <div>
          <Kicker>{t.start.kicker}</Kicker>
          <h2 className="headline mt-2 text-[36px] md:text-[48px]">{t.start.title}</h2>
          <p className="mt-3 text-[17px] leading-relaxed text-fg-2">{t.start.body}</p>
          <ul className="mt-6 grid gap-2 sm:grid-cols-2">
            {t.start.reqs.map((r) => (
              <li key={r} className="flex items-center gap-2 text-[15px] text-fg-2">
                <Check className="size-4 text-lime" /> {r}
              </li>
            ))}
          </ul>
          <p className="mt-6 rounded-xl border border-lime/25 bg-lime/10 px-4 py-3 text-[15px] text-lime-300">{t.start.note}</p>
        </div>
        <div className="flex flex-col justify-center">
          <div className="rounded-[20px] border border-line bg-surface-2">
            <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <span className="flex gap-1.5">
                <span className="size-3 rounded-full bg-surface-5" />
                <span className="size-3 rounded-full bg-surface-5" />
                <span className="size-3 rounded-full bg-surface-5" />
              </span>
              <CopyLine text={"git clone https://github.com/Jjat00/hf-studio.git\ncd hf-studio\n./dev.sh"} />
            </div>
            <pre className="thin-scrollbar overflow-x-auto p-5 font-mono text-[14px] leading-7 text-fg">
              {cmd.split("\n").map((l) => (
                <span key={l} className="block">
                  <span className="text-fg-4">$ </span>
                  {l.split("#")[0]}
                  {l.includes("#") && <span className="text-fg-3">#{l.split("#")[1]}</span>}
                </span>
              ))}
            </pre>
          </div>
          <a href={REPO} className="mt-4 flex items-center justify-center gap-2 self-start rounded-xl bg-lime px-5 py-3 text-[15px] font-semibold text-ink hover:bg-lime-400">
            README <ArrowRight className="size-4" />
          </a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const { t } = useI18n();
  return (
    <footer className="mx-auto w-full max-w-[1400px] px-4 pb-10">
      <div className="grain relative overflow-hidden rounded-[28px] bg-surface-3 px-6 py-16 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/art/text-to-video.webp" alt="" className="absolute inset-0 size-full object-cover opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/70 to-black/85" />
        <div className="relative flex flex-col items-center">
          <Star className="size-10 text-lime" fill="currentColor" />
          <h2 className="headline mt-5 text-[36px] md:text-[56px]">{t.footer.title}</h2>
          <p className="mt-3 max-w-xl text-[17px] text-white/85">{t.footer.body}</p>
          <a href={REPO} className="mt-7 flex items-center gap-2 rounded-xl bg-white px-6 py-3.5 text-[16px] font-semibold text-ink shadow-[inset_0_-3px_0_rgba(0,0,0,0.12)]">
            <GitHubMark className="size-5" /> {t.footer.cta}
          </a>
        </div>
      </div>
      <div className="mt-8 flex flex-col items-center justify-between gap-4 text-[14px] text-fg-3 md:flex-row">
        <div className="flex items-center gap-2.5">
          <Logo size={24} />
          <span className="font-semibold text-fg-2">HF Studio</span>
          <span>· MIT</span>
        </div>
        <p className="max-w-xl text-center">{t.footer.disclaimer}</p>
        <p>
          {t.footer.by}{" "}
          <a href={AUTHOR} className="font-semibold text-fg-2 hover:text-lime">
            Jaime Aza
          </a>
        </p>
      </div>
    </footer>
  );
}

export function Landing() {
  return (
    <>
      <Nav />
      <main className="flex flex-col gap-24 pb-8 md:gap-32">
        <Hero />
        <Promo />
        <Examples />
        <Capabilities />
        <Spaces />
        <Providers />
        <Audio />
        <Agents />
        <More />
        <Start />
      </main>
      <Footer />
    </>
  );
}
