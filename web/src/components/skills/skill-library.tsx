"use client";

import {
  AudioLines,
  Clapperboard,
  FileText,
  FileUp,
  Film,
  FolderUp,
  ImagePlus,
  Loader2,
  Megaphone,
  Package,
  Pencil,
  Plus,
  Search,
  Share2,
  Sparkles,
  Trash2,
  UserRound,
  Wand2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useEffectEvent, useMemo, useRef, useState, type ReactNode } from "react";
import { useI18n } from "@/components/i18n-provider";
import { CreationsPicker } from "@/components/studio/creations-picker";
import { outputSrc, SKILL_CATEGORIES, studio, type SkillCard, type SkillCategory, type SkillSummary } from "@/lib/studio";
import type { Generation } from "@/lib/types";

type Draft = {
  original: string | null;
  slug: string;
  description: string;
  body: string;
  files: { path: string; chars: number }[];
  summary: string;
  category: SkillCategory | "";
  examples: string;
  showcase: string[];
};

const EMPTY: Draft = { original: null, slug: "", description: "", body: "", files: [], summary: "", category: "", examples: "", showcase: [] };
const TEXT_FILE = /\.(md|txt|json|csv|ya?ml)$/i;
const field = "w-full rounded-xl border border-line-2 bg-surface-3 px-3 py-2 text-sm text-fg outline-none focus:border-lime/60";
const MAX_SHOWCASE = 6;
const ICONS: Record<SkillCategory, typeof Wand2> = {
  cine: Clapperboard,
  anuncios: Megaphone,
  personajes: UserRound,
  producto: Package,
  video: Film,
  audio: AudioLines,
  redes: Share2,
  otros: Wand2,
};

const tryHref = (slug: string, example: string) => `/supercomputer?q=${encodeURIComponent(`/${slug} ${example}`)}`;
const categoryOf = (s: SkillSummary): SkillCategory => s.card?.category ?? "otros";

/** Generaciones de muestra de las fichas: se piden una vez por página y se comparten entre tarjetas y ficha. */
function useShowcase(ids: string[]) {
  const [found, setFound] = useState<Record<string, Generation | null>>({});
  const key = ids.join(",");
  useEffect(() => {
    const missing = key ? key.split(",").filter((id) => !(id in found)) : [];
    if (!missing.length) return;
    let alive = true;
    Promise.all(missing.map((id) => studio.get(id).then((g) => [id, g] as const, () => [id, null] as const))).then((pairs) => {
      if (alive) setFound((prev) => ({ ...prev, ...Object.fromEntries(pairs) }));
    });
    return () => {
      alive = false;
    };
  }, [key, found]);
  return found;
}

function Thumb({ g, className }: { g: Generation; className: string }) {
  const out = g.outputs[0];
  if (!out) return null;
  return out.kind === "video" ? (
    <video src={outputSrc(out)} className={className} muted playsInline loop autoPlay preload="metadata" />
  ) : (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={outputSrc(out)} alt="" className={className} />
  );
}

/** Ventana modal accesible: foco dentro (en `[data-autofocus]`), Tab atrapado, Escape cierra y, al cerrar, el foco
 * vuelve a donde estaba. */
function Dialog({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const close = useEffectEvent(onClose);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return close();
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>("a[href], button:not([disabled])")];
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      if (e.shiftKey && (document.activeElement === first || !panel.current.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !panel.current.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={label}>
      <button type="button" tabIndex={-1} aria-hidden="true" onClick={onClose} className="absolute inset-0 bg-black/70" />
      <div ref={panel} className="thin-scrollbar relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-card border border-line bg-surface-1 p-5">
        {children}
      </div>
    </div>
  );
}

/** Galería de skills de Supercomputer: qué hace cada una, pedidos de ejemplo que se prueban con un clic y
 * generaciones de muestra. También crea, edita, importa un SKILL.md y borra. */
export function SkillLibrary() {
  const { t } = useI18n();
  const k = t.skills;
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<SkillCategory | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const picked = useRef<string[]>([]);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const [saving, setSaving] = useState(0);
  const file = useRef<HTMLInputElement>(null);
  const folder = useRef<HTMLInputElement>(null);

  const showcaseIds = useMemo(() => [...new Set((skills ?? []).flatMap((s) => s.card?.showcase ?? []))].sort(), [skills]);
  const showcase = useShowcase(showcaseIds);
  const present = useMemo(() => SKILL_CATEGORIES.filter((c) => skills?.some((s) => categoryOf(s) === c)), [skills]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (skills ?? []).filter(
      (s) =>
        (!category || categoryOf(s) === category) &&
        (!q || [s.slug, s.description, s.card?.summary ?? "", ...(s.card?.examples ?? [])].some((x) => x.toLowerCase().includes(q))),
    );
  }, [skills, query, category]);
  const current = skills?.find((s) => s.slug === opened) ?? null;

  const load = useCallback(() => {
    studio.skills().then(
      (r) => setSkills(r.skills),
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setSkills([]);
      },
    );
  }, []);
  useEffect(load, [load]);

  async function edit(slug: string) {
    setError(null);
    try {
      const s = await studio.skill(slug);
      setOpened(null);
      setDraft({
        original: s.slug,
        slug: s.slug,
        description: s.description,
        body: s.body,
        files: s.files,
        summary: s.card?.summary ?? "",
        category: s.card?.category ?? "",
        examples: (s.card?.examples ?? []).join("\n"),
        showcase: s.card?.showcase ?? [],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    // El formulario no edita las muestras: sin `showcase`, el servidor conserva las vigentes.
    const card: SkillCard = {
      summary: draft.summary.trim() || undefined,
      category: draft.category || undefined,
      examples: draft.examples.split("\n").map((x) => x.trim()).filter(Boolean),
      ...(draft.original ? {} : { showcase: draft.showcase }),
    };
    const body = { slug: draft.slug.trim(), description: draft.description, body: draft.body, card };
    try {
      if (draft.original) await studio.updateSkill(draft.original, body);
      else await studio.createSkill(body);
      setDraft(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function importFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const f of Array.from(files)) await studio.createSkill({ skill_md: await f.text() });
      load();
    } catch (e) {
      setError(`${k.importError}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
      if (file.current) file.current.value = "";
    }
  }

  /** Una carpeta de skill (SKILL.md y references/…): el SKILL.md es el cuerpo, el resto, archivos de referencia. */
  async function importFolder(list: FileList | null) {
    if (!list?.length) return;
    setBusy(true);
    setError(null);
    try {
      const all = Array.from(list).map((f) => ({ f, path: (f.webkitRelativePath || f.name).split("/").slice(1).join("/") || f.name }));
      const main = all.find((x) => x.path === "SKILL.md");
      if (!main) throw new Error(k.noSkillMd);
      const files: Record<string, string> = {};
      for (const x of all) if (x !== main && TEXT_FILE.test(x.path)) files[x.path] = await x.f.text();
      await studio.createSkill({ skill_md: await main.f.text(), files });
      load();
    } catch (e) {
      setError(`${k.importError}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
      if (folder.current) folder.current.value = "";
    }
  }

  /** Cambia las generaciones de muestra de una skill (sin tocar el resto de su ficha). */
  /** Añade o quita muestras de una skill. El servidor aplica cada cambio sobre las muestras guardadas y no toca
   * nada más de la skill; la cola mantiene el orden de los clics. */
  function setShowcase(slug: string, change: { add?: string[]; remove?: string[] }) {
    setError(null);
    setSaving((n) => n + 1);
    queue.current = queue.current
      .then(async () => {
        const saved = await studio.skillShowcase(slug, change);
        setSkills((prev) => prev?.map((x) => (x.slug === slug ? { ...x, card: saved.card } : x)) ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setSaving((n) => n - 1));
  }

  async function remove(slug: string) {
    if (!window.confirm(k.confirmDelete(slug))) return;
    setOpened(null);
    await studio.deleteSkill(slug).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    load();
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline text-[40px] md:text-[56px]">{k.title}</h1>
          <p className="mt-2 max-w-3xl text-fg-3">{k.subtitle}</p>
        </div>
        <div className="flex gap-2">
          <input ref={file} type="file" accept=".md,text/markdown,text/plain" multiple hidden onChange={(e) => importFiles(e.target.files)} />
          <input
            ref={(el) => {
              folder.current = el;
              el?.setAttribute("webkitdirectory", "");
            }}
            type="file"
            multiple
            hidden
            onChange={(e) => importFolder(e.target.files)}
          />
          <button
            type="button"
            onClick={() => folder.current?.click()}
            disabled={busy}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-surface-4 px-3 text-sm text-fg-2 hover:text-fg disabled:opacity-50"
          >
            <FolderUp className="size-4" /> {k.importFolder}
          </button>
          <button
            type="button"
            onClick={() => file.current?.click()}
            disabled={busy}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-surface-4 px-3 text-sm text-fg-2 hover:text-fg disabled:opacity-50"
          >
            <FileUp className="size-4" /> {k.import}
          </button>
          <button
            type="button"
            onClick={() => setDraft({ ...EMPTY })}
            className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink hover:brightness-105"
          >
            <Plus className="size-4" /> {k.create}
          </button>
        </div>
      </div>

      {error && <p className="mt-4 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      {draft && (
        <form
          className="mt-6 space-y-4 rounded-2xl border border-line-2 bg-surface-2 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="block space-y-1">
            <span className="text-sm font-medium text-fg">{k.name}</span>
            <input
              value={draft.slug}
              onChange={(e) => setDraft({ ...draft, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })}
              placeholder="ads-ugc"
              maxLength={63}
              className={`${field} font-mono`}
            />
            <span className="text-xs text-fg-3">{k.nameHint}</span>
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium text-fg">{k.description}</span>
            <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} maxLength={1000} className={field} />
            <span className="text-xs text-fg-3">{k.descriptionHint}</span>
          </label>
          <div className="grid gap-4 md:grid-cols-[1fr_200px]">
            <label className="block space-y-1">
              <span className="text-sm font-medium text-fg">{k.summary}</span>
              <input value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} maxLength={300} className={field} />
              <span className="text-xs text-fg-3">{k.summaryHint}</span>
            </label>
            <label className="block space-y-1">
              <span className="text-sm font-medium text-fg">{k.category}</span>
              <select value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value as SkillCategory | "" })} className={field}>
                <option value="">—</option>
                {SKILL_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {k.categories[c]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block space-y-1">
            <span className="text-sm font-medium text-fg">{k.examplesField}</span>
            <textarea value={draft.examples} onChange={(e) => setDraft({ ...draft, examples: e.target.value })} rows={3} className={field} />
            <span className="text-xs text-fg-3">{k.examplesHint}</span>
          </label>
          <label className="block space-y-1">
            <span className="flex items-center justify-between text-sm font-medium text-fg">
              {k.body}
              <span className="text-xs font-normal text-fg-4">{k.chars(draft.body.length)}</span>
            </span>
            <textarea
              value={draft.body}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
              rows={16}
              maxLength={150000}
              className={`${field} thin-scrollbar font-mono text-[13px] leading-relaxed`}
            />
            <span className="text-xs text-fg-3">{k.bodyHint}</span>
          </label>
          {draft.files.length > 0 && (
            <div className="space-y-1">
              <p className="text-sm font-medium text-fg">{k.filesTitle}</p>
              <ul className="space-y-0.5 text-xs text-fg-3">
                {draft.files.map((f) => (
                  <li key={f.path} className="flex items-center gap-1.5 font-mono">
                    <FileText className="size-3.5" /> {f.path} <span className="text-fg-4">· {k.chars(f.chars)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setDraft(null)} className="h-9 rounded-xl px-3 text-sm text-fg-3 hover:text-fg">
              {k.cancel}
            </button>
            <button
              type="submit"
              disabled={busy || !draft.slug.trim() || !draft.description.trim() || !draft.body.trim()}
              className="flex h-9 items-center gap-1.5 rounded-xl bg-lime px-3.5 text-sm font-semibold text-ink disabled:opacity-40"
            >
              {busy && <Loader2 className="size-4 animate-spin" />} {k.save}
            </button>
          </div>
        </form>
      )}

      {!draft && (
        <div className="mt-6 flex flex-col gap-3 md:flex-row md:items-center">
          <label className="relative md:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-4" />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={k.search} className={`${field} pl-9`} />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {[null, ...present].map((c) => (
              <button
                key={c ?? "all"}
                type="button"
                onClick={() => setCategory(c)}
                className={`h-8 rounded-full px-3 text-sm ${category === c ? "bg-lime font-semibold text-ink" : "bg-surface-3 text-fg-3 hover:text-fg"}`}
              >
                {c ? k.categories[c] : k.all}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        {skills === null ? (
          <div className="shimmer h-40 rounded-xl" />
        ) : skills.length === 0 ? (
          <p className="py-10 text-center text-sm text-fg-3">{k.empty}</p>
        ) : visible.length === 0 ? (
          <p className="py-10 text-center text-sm text-fg-3">{k.noMatch}</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((s) => {
              const Icon = ICONS[categoryOf(s)];
              const thumbs = (s.card?.showcase ?? []).map((id) => showcase[id]).filter((g): g is Generation => !!g && g.outputs.length > 0);
              return (
                <li key={s.slug} className="flex flex-col overflow-hidden rounded-2xl border border-line bg-surface-2">
                  {thumbs.length > 0 && (
                    <button type="button" onClick={() => setOpened(s.slug)} className="grid h-28 grid-cols-3 gap-px bg-line">
                      {thumbs.slice(0, 3).map((g) => (
                        <Thumb key={g.id} g={g} className="size-full object-cover" />
                      ))}
                    </button>
                  )}
                  <div className="flex flex-1 flex-col p-4">
                    <div className="flex items-start gap-3">
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-lime/15 text-lime">
                        <Icon className="size-4" />
                      </span>
                      <button type="button" onClick={() => setOpened(s.slug)} className="min-w-0 flex-1 text-left">
                        <p className="font-mono text-sm font-semibold text-fg">/{s.slug}</p>
                        <p className="mt-1 line-clamp-3 text-sm text-fg-3">{s.card?.summary ?? s.description}</p>
                      </button>
                    </div>
                    {(s.card?.examples?.length ?? 0) > 0 && (
                      <div className="mt-3 flex flex-col gap-1.5">
                        {s.card.examples!.slice(0, 2).map((ex) => (
                          <Link
                            key={ex}
                            href={tryHref(s.slug, ex)}
                            title={k.tryIt}
                            className="flex items-center gap-1.5 truncate rounded-lg bg-surface-3 px-2.5 py-1.5 text-xs text-fg-2 hover:text-fg"
                          >
                            <Sparkles className="size-3.5 shrink-0 text-lime" />
                            <span className="truncate">{ex}</span>
                          </Link>
                        ))}
                      </div>
                    )}
                    <div className="mt-auto flex items-center gap-1 pt-3">
                      <span className="flex-1 text-xs text-fg-4">{s.files.length > 0 ? k.files(s.files.length) : ""}</span>
                      <button type="button" onClick={() => setOpened(s.slug)} className="rounded-lg px-2 py-1 text-xs text-fg-3 hover:text-fg">
                        {k.open}
                      </button>
                      <button type="button" disabled={saving > 0} title={k.edit} aria-label={`${k.edit}: ${s.slug}`} onClick={() => edit(s.slug)} className="rounded-lg p-1.5 text-fg-3 hover:text-fg disabled:opacity-50">
                        <Pencil className="size-4" />
                      </button>
                      <button type="button" title={k.delete} aria-label={`${k.delete}: ${s.slug}`} onClick={() => remove(s.slug)} className="rounded-lg p-1.5 text-fg-3 hover:text-danger">
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {current && !picking && (
        <Dialog label={`/${current.slug}`} onClose={() => setOpened(null)}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-lg font-semibold text-fg">/{current.slug}</p>
                <p className="mt-0.5 text-xs text-fg-4">{k.categories[categoryOf(current)]}</p>
              </div>
              <button type="button" data-autofocus aria-label={k.close} onClick={() => setOpened(null)} className="rounded-lg text-fg-3 hover:text-fg">
                <X className="size-5" />
              </button>
            </div>
            {current.card?.summary && (
              <section className="mt-4">
                <h2 className="text-xs font-semibold tracking-wide text-fg-4 uppercase">{k.whatFor}</h2>
                <p className="mt-1 text-fg">{current.card.summary}</p>
              </section>
            )}
            <section className="mt-4">
              <h2 className="text-xs font-semibold tracking-wide text-fg-4 uppercase">{k.whenToUse}</h2>
              <p className="mt-1 text-sm text-fg-3">{current.description}</p>
              <p className="mt-2 text-xs text-fg-4">{k.howToCall(current.slug)}</p>
            </section>
            <section className="mt-5">
              <h2 className="text-xs font-semibold tracking-wide text-fg-4 uppercase">{k.examples}</h2>
              {(current.card?.examples?.length ?? 0) > 0 ? (
                <div className="mt-2 flex flex-col gap-1.5">
                  {current.card.examples!.map((ex) => (
                    <Link key={ex} href={tryHref(current.slug, ex)} className="flex items-center gap-2 rounded-xl bg-surface-3 px-3 py-2 text-sm text-fg-2 hover:text-fg">
                      <Sparkles className="size-4 shrink-0 text-lime" />
                      <span className="flex-1">{ex}</span>
                      <span className="shrink-0 text-xs text-fg-4">{k.tryIt}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="mt-1 text-sm text-fg-4">{k.noExamples}</p>
              )}
            </section>
            <section className="mt-5">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold tracking-wide text-fg-4 uppercase">{k.showcase}</h2>
                {(current.card?.showcase?.length ?? 0) < MAX_SHOWCASE ? (
                  <button type="button" disabled={saving > 0} onClick={() => setPicking(true)} className="flex items-center gap-1.5 disabled:opacity-50 rounded-lg px-2 py-1 text-xs text-fg-3 hover:text-fg">
                    <ImagePlus className="size-3.5" /> {k.addShowcase}
                  </button>
                ) : (
                  <span className="text-xs text-fg-4">{k.showcaseFull(MAX_SHOWCASE)}</span>
                )}
              </div>
              {(current.card?.showcase?.length ?? 0) > 0 ? (
                <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {current.card.showcase!.map((id) => {
                    const g = showcase[id];
                    return (
                      <div key={id} className="group relative aspect-square overflow-hidden rounded-xl bg-surface-3">
                        {g ? <Thumb g={g} className="size-full object-cover" /> : g === undefined ? <div className="shimmer size-full" /> : null}
                        <button
                          type="button"
                          aria-label={k.removeShowcase}
                          title={k.removeShowcase}
                          onClick={() => setShowcase(current.slug, { remove: [id] })}
                          className="absolute top-1.5 right-1.5 rounded-full bg-black/60 p-1 text-white opacity-80 hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-lime"
                        >
                          <X className="size-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-1 text-sm text-fg-4">{k.noShowcase}</p>
              )}
            </section>
            {current.files.length > 0 && (
              <section className="mt-5">
                <h2 className="text-xs font-semibold tracking-wide text-fg-4 uppercase">{k.filesTitle}</h2>
                <ul className="mt-1 space-y-0.5 text-xs text-fg-3">
                  {current.files.map((f) => (
                    <li key={f.path} className="flex items-center gap-1.5 font-mono">
                      <FileText className="size-3.5" /> {f.path}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" disabled={saving > 0} onClick={() => edit(current.slug)} className="disabled:opacity-50 flex h-9 items-center gap-1.5 rounded-xl bg-surface-4 px-3 text-sm text-fg-2 hover:text-fg">
                <Pencil className="size-4" /> {k.edit}
              </button>
            </div>
        </Dialog>
      )}
      {current && picking && (
        <CreationsPicker
          kind="any"
          max={MAX_SHOWCASE - (current.card?.showcase?.length ?? 0)}
          onPickGeneration={(g) => picked.current.push(g.id)}
          onClose={() => {
            // Se guardan juntas al cerrar: el selector llama a onPickGeneration una vez por generación marcada.
            const added = picked.current;
            picked.current = [];
            setPicking(false);
            if (added.length) setShowcase(current.slug, { add: added });
          }}
        />
      )}
    </div>
  );
}
