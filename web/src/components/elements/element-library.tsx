"use client";

import { Check, Clapperboard, Copy, ImagePlus, Loader2, Plus, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { apiSrc, studio } from "@/lib/studio";
import type { StudioElement } from "@/lib/types";

const NAME = /^[a-z][a-z0-9_]{1,31}$/;

/** Abre el estudio en Video › Referencias con Kling 3.0, el elemento elegido y su @nombre en el prompt. */
export function elementHref(el: StudioElement) {
  const q = new URLSearchParams({
    tab: "create",
    mode: "references",
    model: "kling-video/v3.0/std/text-to-video",
    elements: el.id,
    prompt: el.mention,
  });
  return `/video?${q}`;
}

/** Elementos de HF Studio: personajes, productos o lugares para Kling 3.0 (APIMart y KIE). */
export function ElementLibrary() {
  const { t } = useI18n();
  const e = t.elements;
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // ?image=<url> desde «Usar en… › Crear elemento» de una creación: abre el formulario con esa imagen.
  const fromCreation = useSearchParams().get("image");
  const [creating, setCreating] = useState(!!fromCreation);

  useEffect(() => {
    studio.elements().then(
      (r) => setElements(r.elements),
      (err) => setError(err instanceof Error ? err.message : String(err)),
    );
  }, []);

  async function remove(el: StudioElement) {
    if (!window.confirm(e.removeConfirm(el.name))) return;
    try {
      await studio.deleteElement(el.id);
      setElements((list) => list?.filter((x) => x.id !== el.id) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline text-[40px] md:text-[56px]">{e.title}</h1>
          <p className="mt-2 max-w-2xl text-fg-3">{e.subtitle}</p>
        </div>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex h-10 items-center gap-2 rounded-xl bg-lime px-4 text-sm font-semibold text-ink"
          >
            <Plus className="size-4" />
            {e.create}
          </button>
        )}
      </div>

      {error && <p className="mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {creating && (
        <CreateForm
          initialUrls={fromCreation ? [fromCreation] : []}
          onCancel={() => setCreating(false)}
          onCreated={(el) => {
            setElements((list) => [el, ...(list ?? [])]);
            setCreating(false);
          }}
        />
      )}

      {elements === null ? (
        <div className="shimmer mt-8 h-40 rounded-2xl" />
      ) : elements.length === 0 && !creating ? (
        <p className="mt-8 text-fg-3">{e.empty}</p>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {elements.map((el) => (
            <ElementCard key={el.id} el={el} onDelete={() => remove(el)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ElementCard({ el, onDelete }: { el: StudioElement; onDelete: () => void }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <article className="flex flex-col gap-3 rounded-card border border-line bg-surface-2 p-3">
      <div className="grid grid-cols-4 gap-1.5">
        {el.images.map((src) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={src} src={apiSrc(src)} alt="" className="aspect-square w-full rounded-lg bg-surface-3 object-cover" />
        ))}
      </div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-sm font-semibold text-lime">{el.mention}</p>
          <p className="mt-1 line-clamp-2 text-sm text-fg-2">{el.description}</p>
          <Link
            href={elementHref(el)}
            className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-lg bg-lime px-3 text-xs font-semibold text-ink"
          >
            <Clapperboard className="size-3.5" />
            {t.elements.use}
          </Link>
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            title={t.elements.copy}
            aria-label={t.elements.copy}
            onClick={() => {
              void navigator.clipboard.writeText(el.mention);
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            }}
            className="flex size-8 items-center justify-center rounded-lg bg-glass text-fg-2 hover:text-fg"
          >
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          </button>
          <button
            type="button"
            title={t.elements.remove}
            aria-label={t.elements.remove}
            onClick={onDelete}
            className="flex size-8 items-center justify-center rounded-lg bg-glass text-fg-2 hover:text-danger"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>
    </article>
  );
}

type Item = { url: string; file?: File }; // con `file`: subida local (vista previa blob); sin él: URL propia

function CreateForm({
  initialUrls,
  onCancel,
  onCreated,
}: {
  initialUrls: string[];
  onCancel: () => void;
  onCreated: (el: StudioElement) => void;
}) {
  const { t } = useI18n();
  const e = t.elements;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Cada imagen con su URL de vista previa; se liberan al quitarlas y al cerrar el formulario.
  const [items, setItems] = useState<Item[]>(() => initialUrls.map((url) => ({ url })));
  const live = useRef(items);
  useEffect(() => {
    live.current = items;
  }, [items]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => live.current.forEach((i) => i.file && URL.revokeObjectURL(i.url)), []);

  const valid = NAME.test(name) && description.trim().length > 0 && items.length >= 2 && items.length <= 4;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const files = items.flatMap((i) => (i.file ? [i.file] : []));
      const urls = items.filter((i) => !i.file).map((i) => i.url);
      onCreated(await studio.createElement(name, description.trim(), files, urls));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 flex max-w-2xl flex-col gap-4 rounded-card border border-line bg-surface-2 p-4">
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold text-fg-2">{e.name}</span>
        <input
          value={name}
          onChange={(ev) => setName(ev.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 32))}
          placeholder="zorro_rojo"
          className="h-10 rounded-xl bg-surface-3 px-3 font-mono outline-none"
        />
        <span className="text-xs text-fg-3">{e.nameHint}</span>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold text-fg-2">{e.description}</span>
        <textarea
          value={description}
          onChange={(ev) => setDescription(ev.target.value.slice(0, 500))}
          rows={2}
          placeholder={e.descriptionHint}
          className="resize-none rounded-xl bg-surface-3 p-3 outline-none"
        />
      </label>
      <div className="flex flex-col gap-2 text-sm">
        <span className="font-semibold text-fg-2">{e.images}</span>
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <div key={item.url} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.url} alt="" className="size-20 rounded-lg object-cover" />
              <button
                type="button"
                aria-label={e.remove}
                onClick={() => {
                  if (item.file) URL.revokeObjectURL(item.url);
                  setItems((list) => list.filter((x) => x !== item));
                }}
                className="absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full bg-surface-1 text-fg-2"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
          {items.length < 4 && (
            <label className="flex size-20 cursor-pointer items-center justify-center rounded-lg border border-dashed border-line-2 text-fg-3 hover:text-fg">
              <ImagePlus className="size-5" />
              <input
                type="file"
                accept="image/jpeg,image/png"
                multiple
                className="hidden"
                onChange={(ev) => {
                  const room = 4 - items.length;
                  const picked = Array.from(ev.target.files ?? []).slice(0, room);
                  setItems((list) => [...list, ...picked.map((file) => ({ file, url: URL.createObjectURL(file) }))]);
                  ev.target.value = "";
                }}
              />
            </label>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!valid || busy}
          onClick={save}
          className="flex h-10 items-center gap-2 rounded-xl bg-lime px-4 text-sm font-semibold text-ink disabled:opacity-40"
        >
          {busy && <Loader2 className="size-4 animate-spin" />}
          {busy ? e.saving : e.save}
        </button>
        <button type="button" onClick={onCancel} className="h-10 rounded-xl bg-glass px-4 text-sm text-fg-2 hover:text-fg">
          {t.generation.cancel}
        </button>
      </div>
    </div>
  );
}
