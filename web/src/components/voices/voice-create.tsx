"use client";

import { Loader2, Mic, Square, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Chip } from "@/components/studio/controls";
import { approxUsd, studio } from "@/lib/studio";
import type { VoicePreview } from "@/lib/types";

type Mode = "clone" | "design";
const LANGUAGES = ["es", "en", "pt"];
const field = "w-full rounded-lg border border-line bg-surface-3 px-3 py-2 text-sm outline-none focus:border-lime/60";
const primary =
  "flex h-10 items-center justify-center gap-2 rounded-xl bg-lime px-4 text-sm font-semibold text-ink transition hover:brightness-105 disabled:opacity-50";
const secondary = "flex h-9 items-center gap-2 rounded-xl bg-glass px-3 text-sm text-fg-2 hover:text-fg disabled:opacity-50";

/** Muestra de voz para clonar: archivo subido o grabación del micrófono, con su duración si se conoce. */
type Sample = { id: string; file: File; url: string; seconds: number | null };

/** Crear una voz en la cuenta de ElevenLabs: clonarla con audio o diseñarla con una descripción. */
export function VoiceCreate({ canClone, onCreated }: { canClone?: boolean | null; onCreated: () => void }) {
  const { t } = useI18n();
  const c = t.voices.create;
  const [mode, setMode] = useState<Mode>("clone");
  return (
    <section className="mt-6 flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {(["clone", "design"] as Mode[]).map((m) => (
          <Chip key={m} active={mode === m} onClick={() => setMode(m)}>{c.modes[m]}</Chip>
        ))}
      </div>
      {mode === "clone" ? <CloneForm blocked={canClone === false} onCreated={onCreated} /> : <DesignForm onCreated={onCreated} />}
    </section>
  );
}

function LanguagePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const c = useI18n().t.voices.create;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-fg-3">{c.language}</span>
      {LANGUAGES.map((l) => (
        <Chip key={l} active={value === l} onClick={() => onChange(l)}>{c.languages[l]}</Chip>
      ))}
    </div>
  );
}

function audioSeconds(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement(file.type.startsWith("video") ? "video" : "audio");
    const done = (v: number | null) => {
      URL.revokeObjectURL(url);
      resolve(v);
    };
    el.preload = "metadata";
    el.onloadedmetadata = () => done(Number.isFinite(el.duration) ? el.duration : null);
    el.onerror = () => done(null);
    el.src = url;
  });
}

function CloneForm({ blocked, onCreated }: { blocked: boolean; onCreated: () => void }) {
  const c = useI18n().t.voices.create;
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [samples, setSamples] = useState<Sample[]>([]);
  const [removeNoise, setRemoveNoise] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ name: string; verify: boolean } | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const [recordStart, setRecordStart] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const input = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (recordStart === null) return;
    const id = setInterval(() => setElapsed(Math.round((Date.now() - recordStart) / 1000)), 500);
    return () => clearInterval(id);
  }, [recordStart]);

  useEffect(() => () => recorder.current?.stream.getTracks().forEach((tr) => tr.stop()), []);

  async function addFiles(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      const seconds = await audioSeconds(file);
      setSamples((s) => [...s, { id: crypto.randomUUID(), file, url: URL.createObjectURL(file), seconds }]);
    }
  }

  async function startRecording() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: false } });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      const started = Date.now();
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        const type = rec.mimeType || "audio/webm";
        const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
        const file = new File(chunks, `grabacion-${samples.length + 1}.${ext}`, { type });
        // Las grabaciones de MediaRecorder no traen duración en los metadatos: se usa el tiempo grabado.
        setSamples((s) => [...s, { id: crypto.randomUUID(), file, url: URL.createObjectURL(file), seconds: (Date.now() - started) / 1000 }]);
        setRecordStart(null);
      };
      recorder.current = rec;
      rec.start();
      setElapsed(0);
      setRecordStart(started);
    } catch {
      setError(c.micError);
    }
  }

  function stopRecording() {
    recorder.current?.stop();
    recorder.current = null;
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const r = await studio.cloneVoice({ name: name.trim(), files: samples.map((s) => s.file), language, removeNoise, consent });
      setDone({ name: r.name, verify: r.requires_verification });
      setSamples([]);
      onCreated();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // ElevenLabs responde en inglés que el plan no incluye clonar: se dice en el idioma de la UI.
      setError(/instant voice cloning/i.test(msg) ? c.noClonePlan : msg);
    } finally {
      setBusy(false);
    }
  }

  const total = samples.reduce((acc, s) => acc + (s.seconds ?? 0), 0);
  const recording = recordStart !== null;
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <p className="text-xs text-fg-3">{c.cloneHint}</p>
      <label className="flex flex-col gap-1 text-[13px] text-fg-3">
        {c.name}
        <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder={c.namePlaceholder} className={field} />
      </label>
      <LanguagePicker value={language} onChange={setLanguage} />

      <div className="rounded-2xl border border-line bg-surface-3 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-auto text-[13px] text-fg-3">{c.samples}</span>
          <input ref={input} type="file" accept="audio/*,video/*" multiple hidden onChange={(e) => { void addFiles(e.target.files); e.target.value = ""; }} />
          <button type="button" className={secondary} onClick={() => input.current?.click()} disabled={recording}>
            <Upload className="size-4" />
            {c.addFiles}
          </button>
          {recording ? (
            <button type="button" className={`${secondary} text-danger`} onClick={stopRecording}>
              <Square className="size-4" />
              {c.stopRecording} · {elapsed} s
            </button>
          ) : (
            <button type="button" className={secondary} onClick={() => void startRecording()}>
              <Mic className="size-4" />
              {c.record}
            </button>
          )}
        </div>
        {samples.length > 0 && (
          <ul className="mt-3 flex flex-col gap-2">
            {samples.map((s) => (
              <li key={s.id} className="flex items-center gap-3 text-sm">
                <audio controls src={s.url} className="h-8 min-w-0 flex-1" />
                <span className="w-40 truncate text-xs text-fg-3" title={s.file.name}>{s.file.name}</span>
                <span className="w-12 text-right text-xs text-fg-3 tabular-nums">{s.seconds != null ? `${Math.round(s.seconds)} s` : ""}</span>
                <button type="button" aria-label={c.remove} onClick={() => { URL.revokeObjectURL(s.url); setSamples((all) => all.filter((x) => x.id !== s.id)); }} className="text-fg-3 hover:text-fg">
                  <X className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {samples.length > 0 && <p className="mt-2 text-xs text-fg-3 tabular-nums">{c.total(Math.round(total))}</p>}
        {recording && <p className="mt-2 text-xs text-danger">{c.recording(elapsed)}</p>}
        <details className="mt-3 text-xs text-fg-3">
          <summary className="cursor-pointer">{c.readThis}</summary>
          <p className="mt-2 leading-relaxed text-fg-2">{c.readText}</p>
        </details>
      </div>

      <label className="flex items-start gap-2 text-sm text-fg-2">
        <input type="checkbox" checked={removeNoise} onChange={(e) => setRemoveNoise(e.target.checked)} className="mt-1" />
        {c.removeNoise}
      </label>
      <label className="flex items-start gap-2 text-sm text-fg-2">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
        {c.consent}
      </label>
      <div>
        <button type="button" className={primary} disabled={blocked || busy || recording || !name.trim() || !samples.length || !consent} onClick={() => void submit()}>
          {busy && <Loader2 className="size-4 animate-spin" />}
          {busy ? c.cloning : c.clone}
        </button>
      </div>
      {(blocked || error === c.noClonePlan) && (
        <p className="rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-fg-2">
          {c.noClonePlan}{" "}
          <a href="https://elevenlabs.io/pricing" target="_blank" rel="noreferrer" className="text-lime hover:underline">{c.seePlans}</a>
        </p>
      )}
      {error && error !== c.noClonePlan && <p className="text-sm text-danger">{error}</p>}
      {done && (
        <p className="text-sm text-lime">
          {c.cloned(done.name)} {done.verify && c.verify}
        </p>
      )}
    </div>
  );
}

function DesignForm({ onCreated }: { onCreated: () => void }) {
  const c = useI18n().t.voices.create;
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("es");
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<{ key: string; usd: number | null; voice_quote: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previews, setPreviews] = useState<VoicePreview[]>([]);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  const ownText = text.trim();
  const body = { description: description.trim(), language, ...(ownText ? { text: ownText } : {}) };
  const textOk = !ownText || (ownText.length >= 100 && ownText.length <= 1000);
  const valid = body.description.length >= 20 && textOk && (ownText || language !== "pt");

  // Cualquier cambio invalida la cotización: el servidor solo acepta la de esta misma petición.
  const key = JSON.stringify(body);
  const quote = quoted?.key === key ? quoted : null;

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function quoteIt() {
    const r = await run(() => studio.designEstimate(body));
    if (r) setQuoted({ key, usd: r.usd, voice_quote: r.voice_quote });
  }

  async function generate() {
    if (!quote) return;
    const r = await run(() => studio.designVoice({ ...body, voice_quote: quote.voice_quote }));
    setQuoted(null);
    if (r) {
      setPreviews(r.previews);
      setSaved(null);
    }
  }

  async function save(p: VoicePreview) {
    setSaving(p.generated_voice_id);
    setError(null);
    try {
      const r = await studio.saveVoice({ generated_voice_id: p.generated_voice_id, name: name.trim(), description: body.description, language });
      setSaved(r.name);
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <p className="text-xs text-fg-3">{c.designHint}</p>
      <label className="flex flex-col gap-1 text-[13px] text-fg-3">
        {c.description}
        <textarea value={description} maxLength={1000} rows={3} onChange={(e) => setDescription(e.target.value)} placeholder={c.descriptionPlaceholder} className={`${field} resize-none`} />
        {description && description.trim().length < 20 && <span className="text-xs text-danger">{c.tooShort}</span>}
      </label>
      <LanguagePicker value={language} onChange={setLanguage} />
      <label className="flex flex-col gap-1 text-[13px] text-fg-3">
        {c.ownText}
        <textarea value={text} maxLength={1000} rows={3} onChange={(e) => setText(e.target.value)} className={`${field} resize-none`} />
        {(!textOk || (!ownText && language === "pt")) && <span className="text-xs text-danger">{c.textLength}</span>}
      </label>
      <div className="flex flex-wrap gap-2">
        {quote ? (
          <button type="button" className={primary} disabled={busy} onClick={() => void generate()}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {busy ? c.generating : c.generate(quote.usd != null ? approxUsd(quote.usd) : "?")}
          </button>
        ) : (
          <button type="button" className={secondary} disabled={busy || !valid} onClick={() => void quoteIt()}>
            {busy && <Loader2 className="size-4 animate-spin" />}
            {c.quote}
          </button>
        )}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}

      {previews.length > 0 && (
        <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface-3 px-4 py-3">
          <label className="flex flex-col gap-1 text-[13px] text-fg-3">
            {c.name}
            <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} placeholder={c.namePlaceholder} className={field} />
          </label>
          <ul className="flex flex-col gap-2">
            {previews.map((p, i) => (
              <li key={p.generated_voice_id} className="flex flex-wrap items-center gap-3">
                <span className="w-20 text-sm font-semibold">{c.sample(i + 1)}</span>
                <audio controls src={studio.previewUrl(p.preview_url)} className="h-8 min-w-0 flex-1" />
                <button type="button" className={secondary} disabled={!name.trim() || saving !== null} onClick={() => void save(p)}>
                  {saving === p.generated_voice_id && <Loader2 className="size-4 animate-spin" />}
                  {saving === p.generated_voice_id ? c.saving : c.save}
                </button>
              </li>
            ))}
          </ul>
          {saved && <p className="text-sm text-lime">{c.saved(saved)}</p>}
        </div>
      )}
    </div>
  );
}
