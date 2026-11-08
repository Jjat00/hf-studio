"use client";

import { Film, Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio, type KatanaProject } from "@/lib/studio";
import { KatanaModal } from "./media-sources";

/** «Publicar preset»: aquí no hay comunidad, así que guarda la referencia como preset propio (analizado gratis). */
export function PublishModal({ onClose, onSaved }: { onClose: () => void; onSaved: (p: KatanaProject) => void }) {
  const { t } = useI18n();
  const k = t.katana;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);

  function choose(f: File | undefined) {
    if (!f || !f.type.startsWith("video/")) return;
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    if (!name) setName(f.name.replace(/\.[^.]+$/, "").slice(0, 120));
  }

  async function save() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const up = await studio.upload(file);
      onSaved(await studio.katanaCreate(up.url, name.trim() || undefined));
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <KatanaModal title={k.publishTitle} onClose={() => !busy && onClose()} wide={false}
      footer={
        <button type="button" onClick={save} disabled={!file || busy}
          className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-lime px-6 text-[17px] font-semibold text-black hover:bg-lime-400 disabled:opacity-50">
          {busy && <Loader2 className="size-4 animate-spin" />}
          {busy ? k.analyzing : k.publishConfirm}
        </button>
      }>
      <div className="mx-auto max-w-2xl space-y-5 py-2">
        <div className="text-center">
          <p className="text-2xl font-black uppercase tracking-tight">{k.publishKicker}</p>
          <p className="mt-2 text-fg-3">{k.publishBody}</p>
        </div>
        {error && <p className="rounded-2xl border border-danger/50 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
        <button type="button" onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); choose(e.dataTransfer.files[0]); }}
          className="flex h-72 w-full items-center justify-center overflow-hidden rounded-2xl border-2 border-dashed border-white/15 bg-surface-4/60 hover:bg-white/5">
          {preview ? (
            <video src={preview} muted loop autoPlay playsInline className="h-full w-auto object-contain" />
          ) : (
            <span className="flex flex-col items-center gap-3 px-6 text-center">
              <span className="flex size-16 items-center justify-center rounded-full bg-surface-5"><Film className="size-6" /></span>
              <span className="text-lg font-semibold">{k.publishDrop}</span>
              <span className="text-sm text-fg-3">{k.publishDropHint}</span>
            </span>
          )}
        </button>
        <input ref={input} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
        <label className="block space-y-2">
          <span className="text-[15px] font-semibold">{k.presetName}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={120}
            className="h-12 w-full rounded-xl bg-surface-4 px-4 outline-none focus:ring-1 focus:ring-white/20" />
        </label>
      </div>
    </KatanaModal>
  );
}
