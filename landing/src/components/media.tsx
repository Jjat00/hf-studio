"use client";

import clsx from "clsx";
import { Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** Un solo audio suena a la vez en toda la página. */
let current: HTMLAudioElement | null = null;
function claim(a: HTMLAudioElement) {
  if (current && current !== a) current.pause();
  current = a;
}

/** Video en bucle y sin sonido que solo se reproduce cuando está a la vista. */
export function LoopVideo({ src, poster, className }: { src: string; poster: string; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? v.play().catch(() => {}) : v.pause()), { threshold: 0.2 });
    io.observe(v);
    return () => io.disconnect();
  }, []);
  return <video ref={ref} src={src} poster={poster} muted loop playsInline preload="none" className={className} />;
}

function Bars({ on }: { on: boolean }) {
  return (
    <span className="flex h-5 items-end gap-[3px]" aria-hidden>
      {[0, 0.2, 0.4, 0.1, 0.3].map((d, i) => (
        <span
          key={i}
          className={clsx("w-[3px] rounded-full bg-lime", on ? "eq-bar" : "")}
          style={{ height: on ? "100%" : `${30 + i * 8}%`, animationDelay: `${d}s` }}
        />
      ))}
    </span>
  );
}

/** Reproductor compacto con barra de progreso. */
export function AudioPlayer({ src, label, sub }: { src: string; label: string; sub?: string }) {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const toggle = () => {
    const a = ref.current;
    if (!a) return;
    if (a.paused) {
      claim(a);
      a.play().catch(() => {});
    } else a.pause();
  };
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line bg-surface-3 p-3">
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? "Pause" : "Play"}
        className="grid size-11 shrink-0 place-items-center rounded-xl bg-lime text-ink transition-transform active:scale-95"
      >
        {playing ? <Pause className="size-5" fill="currentColor" /> : <Play className="size-5 translate-x-px" fill="currentColor" />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <p className="truncate text-[15px] font-semibold">{label}</p>
          <Bars on={playing} />
        </div>
        {sub && <p className="truncate text-[13px] text-fg-3">{sub}</p>}
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-5">
          <div className="h-full rounded-full bg-lime" style={{ width: `${progress * 100}%` }} />
        </div>
      </div>
      <audio
        ref={ref}
        src={src}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setProgress(0);
        }}
        onTimeUpdate={(e) => {
          const a = e.currentTarget;
          if (a.duration) setProgress(a.currentTime / a.duration);
        }}
      />
    </div>
  );
}

/** Botón de efecto: suena al tocarlo. */
export function SfxPad({ src, label }: { src: string; label: string }) {
  const ref = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        const a = ref.current;
        if (!a) return;
        claim(a);
        a.currentTime = 0;
        a.play().catch(() => {});
      }}
      className={clsx(
        "flex items-center justify-between gap-2 rounded-xl border px-3.5 py-3 text-left text-[14px] font-medium transition-colors",
        playing ? "border-lime/60 bg-lime/10 text-lime" : "border-line bg-surface-3 text-fg-2 hover:border-line-2 hover:text-fg",
      )}
    >
      <span className="truncate">{label}</span>
      <Bars on={playing} />
      <audio ref={ref} src={src} preload="none" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} />
    </button>
  );
}

/** Antes y después del cambio de voz: dos videos sincronizados; el interruptor elige cuál suena. */
export function VoiceCompare({ before, after, labels }: { before: string; after: string; labels: { before: string; after: string; hint: string } }) {
  const a = useRef<HTMLVideoElement>(null);
  const b = useRef<HTMLVideoElement>(null);
  const [side, setSide] = useState<"before" | "after">("after");
  const [sound, setSound] = useState(false);
  const [playing, setPlaying] = useState(false);

  const sync = () => {
    if (a.current && b.current && Math.abs(a.current.currentTime - b.current.currentTime) > 0.15) b.current.currentTime = a.current.currentTime;
  };
  const play = () => {
    const va = a.current;
    const vb = b.current;
    if (!va || !vb) return;
    if (current) current.pause();
    if (va.paused) {
      vb.currentTime = va.currentTime;
      va.play().catch(() => {});
      vb.play().catch(() => {});
    } else {
      va.pause();
      vb.pause();
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="relative mx-auto aspect-[9/16] w-full max-w-[300px] overflow-hidden rounded-[20px] bg-surface-3">
        <video
          ref={a}
          src={before}
          poster={before.replace(".mp4", ".jpg")}
          playsInline
          loop
          preload="none"
          muted={!sound || side !== "before"}
          onTimeUpdate={sync}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          className={clsx("absolute inset-0 size-full object-cover transition-opacity", side === "before" ? "opacity-100" : "opacity-0")}
        />
        <video
          ref={b}
          src={after}
          poster={after.replace(".mp4", ".jpg")}
          playsInline
          loop
          preload="none"
          muted={!sound || side !== "after"}
          className={clsx("absolute inset-0 size-full object-cover transition-opacity", side === "after" ? "opacity-100" : "opacity-0")}
        />
        <button type="button" onClick={play} aria-label={playing ? "Pause" : "Play"} className="absolute inset-0 grid place-items-center">
          {!playing && (
            <span className="grid size-16 place-items-center rounded-full bg-black/55 backdrop-blur">
              <Play className="size-7 translate-x-0.5" fill="currentColor" />
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setSound((s) => !s)}
          aria-label={sound ? "Mute" : "Unmute"}
          className="absolute top-3 right-3 grid size-9 place-items-center rounded-full bg-black/55 backdrop-blur"
        >
          {sound ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />}
        </button>
      </div>
      <div className="mx-auto grid w-full max-w-[300px] grid-cols-2 gap-1 rounded-xl bg-surface-3 p-1">
        {(["before", "after"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSide(s)}
            className={clsx("rounded-lg py-2 text-[14px] font-semibold transition-colors", side === s ? "bg-lime text-ink" : "text-fg-2 hover:text-fg")}
          >
            {labels[s]}
          </button>
        ))}
      </div>
      <p className="text-center text-[13px] text-fg-3">{labels.hint}</p>
    </div>
  );
}
