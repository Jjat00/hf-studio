"use client";

import { BarChart3, Clock, Loader2, Maximize, Plus, Volume2, VolumeX } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { costShort, studio, type Estimate } from "@/lib/studio";

const MODEL = "bytedance/seedance-2.0/text-to-video";
const DURATIONS = [5, 8, 10, 15];
const RATIOS = ["16:9", "9:16", "1:1", "21:9"];

/** Barra de prompt de la portada: genera un texto a video con Seedance 2.0 y lleva al estudio. */
export function HeroPrompt() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(8);
  const [ratio, setRatio] = useState("16:9");
  const [audio, setAudio] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string | null>(null);
  const input = { prompt: "cost preview", duration, aspect_ratio: ratio, generate_audio: audio, resolution: "720p" };
  const inputKey = JSON.stringify(input);
  const [cost, setCost] = useState<{ key: string; value: Estimate } | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      studio
        .estimate(MODEL, JSON.parse(inputKey))
        .then((value) => setCost({ key: inputKey, value }))
        .catch(() => undefined);
    }, 400);
    return () => clearTimeout(t);
  }, [inputKey]);
  const price = cost?.key === inputKey ? costShort(cost.value) : null;

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!prompt.trim() || busy || !price) return; // sin precio visible no se genera
    setBusy(true);
    setError(null);
    key.current ??= crypto.randomUUID();
    try {
      await studio.generate(MODEL, { prompt, duration, aspect_ratio: ratio, generate_audio: audio, resolution: "720p" }, key.current);
      router.push("/video?tab=create&mode=text");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      key.current = null;
      setBusy(false);
    }
  }

  const cycle = <T,>(list: T[], v: T) => list[(list.indexOf(v) + 1) % list.length];
  const chip = "flex h-8 items-center gap-1.5 rounded-lg bg-glass px-2.5 text-xs font-semibold whitespace-nowrap hover:bg-white/10";

  return (
    <form onSubmit={submit} className="pointer-events-auto mt-8 flex w-full max-w-[702px] items-end gap-3 p-3">
      <div className="min-w-0 flex-1 rounded-2xl bg-surface-3/95 p-4 backdrop-blur-md">
        <div className="flex items-start gap-3">
          <button type="button" onClick={() => router.push("/video?tab=create&mode=frames")} className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-glass" aria-label="Añadir imagen">
            <Plus className="size-4" />
          </button>
          <textarea
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              key.current = null;
            }}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
            placeholder="Describe any visual idea. We will generate a video."
            className="hide-scrollbar h-12 min-w-0 flex-1 resize-none bg-transparent text-[16px] tracking-[-0.01em] outline-none placeholder:text-fg-3"
          />
        </div>
        <div className="hide-scrollbar mt-1 flex gap-1.5 overflow-x-auto">
          <span className={chip}>
            <BarChart3 className="size-3.5" /> Seedance 2.0
          </span>
          <button type="button" className={chip} onClick={() => setDuration(cycle(DURATIONS, duration))}>
            <Clock className="size-3.5" /> {duration}s
          </button>
          <button type="button" className={chip} onClick={() => setRatio(cycle(RATIOS, ratio))}>
            <Maximize className="size-3.5" /> {ratio}
          </button>
          <button type="button" className={chip} onClick={() => setAudio(!audio)}>
            {audio ? <Volume2 className="size-3.5" /> : <VolumeX className="size-3.5" />} {audio ? "On" : "Off"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      </div>
      <button
        type="submit"
        disabled={busy || !prompt.trim() || !price}
        className="font-display flex h-20 min-w-30 shrink-0 items-center justify-center rounded-xl border border-white/5 bg-gradient-to-b from-[#e3ff4d] to-lime px-6 text-xs font-bold tracking-[-0.04em] text-ink uppercase shadow-[inset_0_-4px_0_rgba(80,100,0,0.3),10px_34px_24px_rgba(0,0,0,0.15)] disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="size-5 animate-spin" />
        ) : (
          <span className="flex flex-col items-center leading-tight">
            Generate
            <span className="text-[11px] font-semibold tracking-normal normal-case opacity-70">{price ?? "…"}</span>
          </span>
        )}
      </button>
    </form>
  );
}
