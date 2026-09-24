"use client";

import clsx from "clsx";
import { AudioLines, ImageIcon, Link2, Loader2, Plus, Video, X } from "lucide-react";
import { useRef, useState } from "react";
import { probeDuration } from "@/lib/media";
import { studio } from "@/lib/studio";

type Kind = "image" | "video" | "audio";

const ACCEPT: Record<Kind, string> = {
  image: "image/jpeg,image/png,image/webp,image/gif",
  video: "video/mp4",
  audio: "audio/wav,audio/x-wav",
};
const ICON = { image: ImageIcon, video: Video, audio: AudioLines };

/** Vista previa local de lo subido en esta sesión; lo reutilizado se muestra con su URL remota. */
const previews = new Map<string, string>();

function Thumb({ url, kind, onRemove }: { url: string; kind: Kind; onRemove: () => void }) {
  const src = previews.get(url) ?? url;
  return (
    <div className="group relative size-full overflow-hidden rounded-xl bg-surface-4">
      {kind === "video" ? (
        <video src={src} className="size-full object-cover" muted loop autoPlay playsInline />
      ) : kind === "image" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt="" className="size-full object-cover" />
      ) : (
        <div className="flex size-full items-center justify-center">
          <AudioLines className="size-6 text-lime" />
        </div>
      )}
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove"
        className="absolute top-2 right-2 flex size-7 items-center justify-center rounded-lg bg-black/60 text-white opacity-0 backdrop-blur transition-opacity group-hover:opacity-100"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}

export function MediaSlot({
  label,
  hint,
  kind,
  multiple,
  max,
  required,
  value,
  onChange,
  compact,
  error,
}: {
  label: string;
  hint: string;
  kind: Kind;
  multiple: boolean;
  max: number;
  required: boolean;
  value: string | string[] | undefined;
  onChange: (v: string | string[] | undefined) => void;
  compact?: boolean;
  error?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pasting, setPasting] = useState(false);
  const urls = Array.isArray(value) ? value : value ? [value] : [];
  const Icon = ICON[kind];
  const full = urls.length >= max;

  const set = (next: string[]) => onChange(multiple ? (next.length ? next : undefined) : next[0]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploadError(null);
    const list = Array.from(files).slice(0, Math.max(0, max - urls.length) || 1);
    setBusy((b) => b + list.length);
    const done: string[] = [];
    for (const file of list) {
      try {
        const res = await studio.upload(file);
        previews.set(res.url, URL.createObjectURL(file));
        // Mide la duración con el archivo local (sin descargarlo de nuevo) para cotizar.
        if (kind === "video") probeDuration(previews.get(res.url)!, res.url);
        done.push(res.url);
      } catch (e) {
        setUploadError(e instanceof Error ? e.message : "Upload failed");
      } finally {
        setBusy((b) => b - 1);
      }
    }
    if (done.length) set(multiple ? [...urls, ...done].slice(0, max) : done.slice(-1));
  }

  const picker = (
    <input
      ref={input}
      type="file"
      hidden
      accept={ACCEPT[kind]}
      multiple={multiple}
      onChange={(e) => {
        upload(e.target.files);
        e.target.value = "";
      }}
    />
  );

  const emptyTile = (
    <div
      role="button"
      tabIndex={0}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        upload(e.dataTransfer.files);
      }}
      className={clsx(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border bg-surface-3 px-4 text-center transition-colors hover:bg-surface-4",
        error ? "border-danger/60" : "border-line",
        compact ? "h-[208px]" : "h-[196px]",
      )}
    >
      <span className="flex size-12 items-center justify-center rounded-full bg-surface-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
        {busy ? <Loader2 className="size-5 animate-spin text-lime" /> : <Icon className="size-5" />}
      </span>
      <div>
        <p className="text-[15px] font-semibold">
          {label}
          {!required && <span className="font-normal text-fg-3"> · optional</span>}
        </p>
        <p className="mt-1 text-[13px] leading-snug text-fg-3">{busy ? "Uploading…" : hint}</p>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-2">
      {picker}
      {urls.length === 0 ? (
        emptyTile
      ) : (
        <div className="rounded-2xl border border-line bg-surface-3 p-2">
          <div className="mb-2 flex items-center justify-between px-1.5 pt-1">
            <p className="text-[13px] font-semibold">{label}</p>
            <p className="text-xs text-fg-3">
              {urls.length}/{max}
            </p>
          </div>
          <div className={clsx("grid gap-2", multiple ? "grid-cols-3" : "grid-cols-1")}>
            {urls.map((u) => (
              <div key={u} className={multiple ? "aspect-square" : "aspect-video"}>
                <Thumb url={u} kind={kind} onRemove={() => set(urls.filter((x) => x !== u))} />
              </div>
            ))}
            {multiple && !full && (
              <button
                type="button"
                onClick={() => input.current?.click()}
                className="flex aspect-square items-center justify-center rounded-xl border border-dashed border-line-2 text-fg-3 hover:text-fg"
              >
                {busy ? <Loader2 className="size-5 animate-spin" /> : <Plus className="size-5" />}
              </button>
            )}
          </div>
        </div>
      )}
      <div className="flex items-center justify-between px-1">
        {pasting ? (
          <form
            className="flex w-full gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const url = String(new FormData(e.currentTarget).get("url") ?? "").trim();
              if (/^https?:\/\//.test(url)) set(multiple ? [...urls, url].slice(0, max) : [url]);
              setPasting(false);
            }}
          >
            <input
              name="url"
              autoFocus
              placeholder="https://…"
              className="min-w-0 flex-1 rounded-lg bg-surface-4 px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-lime"
            />
            <button className="rounded-lg bg-glass px-2.5 text-sm font-medium">Use</button>
          </form>
        ) : (
          !full && (
            <button
              type="button"
              onClick={() => setPasting(true)}
              className="flex items-center gap-1 text-xs text-fg-3 hover:text-fg-2"
            >
              <Link2 className="size-3.5" /> Paste public URL
            </button>
          )
        )}
      </div>
      {(uploadError || error) && <p className="px-1 text-xs text-danger">{uploadError ?? error}</p>}
    </div>
  );
}
