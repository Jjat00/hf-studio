"use client";

import { FileUp, Loader2, Pencil, Plus, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio, type SkillSummary } from "@/lib/studio";

type Draft = { original: string | null; slug: string; description: string; body: string };

const EMPTY: Draft = { original: null, slug: "", description: "", body: "" };
const field = "w-full rounded-xl border border-line-2 bg-surface-3 px-3 py-2 text-sm text-fg outline-none focus:border-lime/60";

/** Biblioteca de skills de Supercomputer: crear, editar, importar un SKILL.md y borrar. */
export function SkillLibrary() {
  const { t } = useI18n();
  const k = t.skills;
  const [skills, setSkills] = useState<SkillSummary[] | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

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
      setDraft({ original: s.slug, slug: s.slug, description: s.description, body: s.body });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    const body = { slug: draft.slug.trim(), description: draft.description, body: draft.body };
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

  async function remove(slug: string) {
    if (!window.confirm(k.confirmDelete(slug))) return;
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
          <label className="block space-y-1">
            <span className="flex items-center justify-between text-sm font-medium text-fg">
              {k.body}
              <span className="text-xs font-normal text-fg-4">{k.chars(draft.body.length)}</span>
            </span>
            <textarea
              value={draft.body}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
              rows={16}
              maxLength={60000}
              className={`${field} thin-scrollbar font-mono text-[13px] leading-relaxed`}
            />
            <span className="text-xs text-fg-3">{k.bodyHint}</span>
          </label>
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

      <div className="mt-6">
        {skills === null ? (
          <div className="shimmer h-40 rounded-xl" />
        ) : skills.length === 0 ? (
          <p className="py-10 text-center text-sm text-fg-3">{k.empty}</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {skills.map((s) => (
              <li key={s.slug} className="flex items-start gap-3 rounded-2xl border border-line bg-surface-2 p-4">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-lime/15 text-lime">
                  <Wand2 className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-mono text-sm font-semibold text-fg">/{s.slug}</p>
                  <p className="mt-1 line-clamp-3 text-sm text-fg-3">{s.description}</p>
                </div>
                <button type="button" title={k.edit} aria-label={`${k.edit}: ${s.slug}`} onClick={() => edit(s.slug)} className="rounded-lg p-1.5 text-fg-3 hover:text-fg">
                  <Pencil className="size-4" />
                </button>
                <button type="button" title={k.delete} aria-label={`${k.delete}: ${s.slug}`} onClick={() => remove(s.slug)} className="rounded-lg p-1.5 text-fg-3 hover:text-danger">
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
