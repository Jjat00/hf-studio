"use client";

import clsx from "clsx";
import { Bot, FileText, Loader2, Pencil, Plus, Trash2, User } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Markdown } from "@/components/supercomputer/chat-panel";
import { studio, StudioError, type ProjectDoc, type ProjectDocKind, type ProjectDocSummary } from "@/lib/studio";

const KINDS: ProjectDocKind[] = ["treatment", "breakdown", "bible", "lookbook", "color_script", "blocking", "script", "notes", "other"];

type Draft = { title: string; kind: ProjectDocKind; markdown: string };
type SaveState = "saved" | "saving" | "unsaved" | "conflict";

/**
 * Borrador de un documento que se guarda solo, uno tras otro (como el brief): cada guardado manda la versión que
 * conoce y, si AI Director lo cambió mientras tanto, se detiene en «conflicto» en vez de pisarlo.
 */
function useDocDraft(onSaved: (doc: ProjectDoc) => void, untitled: string) {
  const [doc, setDoc] = useState<ProjectDoc | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [state, setState] = useState<SaveState>("saved");
  const latest = useRef<Draft | null>(null);
  const server = useRef<{ id: string; version: number; draft: Draft } | null>(null);
  const inFlight = useRef(false);

  const init = useCallback((d: ProjectDoc) => {
    const value = { title: d.title, kind: d.kind, markdown: d.markdown };
    server.current = { id: d.id, version: d.version, draft: value };
    latest.current = value;
    setDoc(d);
    setDraft(value);
    setState("saved");
  }, []);

  const same = (a: Draft | null, b: Draft | null) => !!a && !!b && a.title === b.title && a.kind === b.kind && a.markdown === b.markdown;

  const flush = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      while (server.current && latest.current && !same(latest.current, server.current.draft)) {
        const next = latest.current;
        const base = server.current;
        setState("saving");
        try {
          const saved = await studio.updateDocument(base.id, { ...next, title: next.title.trim() || untitled, base_version: base.version });
          server.current = { id: saved.id, version: saved.version, draft: next };
          setDoc(saved);
          onSaved(saved);
        } catch (e) {
          setState(e instanceof StudioError && e.status === 409 ? "conflict" : "unsaved");
          return;
        }
      }
      setState("saved");
    } finally {
      inFlight.current = false;
    }
  }, [onSaved, untitled]);

  useEffect(() => {
    latest.current = draft;
    if (!draft || !server.current || same(draft, server.current.draft)) return;
    const timer = setTimeout(() => void flush(), 1000);
    return () => clearTimeout(timer);
  }, [draft, flush]);

  const change = useCallback((patch: Partial<Draft>) => {
    setDraft((d) => (d ? { ...d, ...patch } : d));
    setState((s) => (s === "conflict" ? s : "unsaved"));
  }, []);

  return { doc, draft, state, init, change, retry: flush, dirty: state !== "saved" };
}

/** Documentos vivos del proyecto (tratamiento, desglose, biblia…): lista y editor en Markdown. */
export function ProjectDocuments({ projectId, revision }: { projectId: string; revision: number }) {
  const { t } = useI18n();
  const p = t.production;
  const [docs, setDocs] = useState<ProjectDocSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onSaved = useCallback((d: ProjectDoc) => setDocs((list) => list?.map((x) => (x.id === d.id ? d : x)) ?? list), []);
  const { doc, draft, state, init, change, retry, dirty } = useDocDraft(onSaved, p.untitled);

  const open = useCallback(
    (id: string) => {
      setSelected(id);
      studio.document(id).then(init, (e) => setError(e instanceof Error ? e.message : String(e)));
    },
    [init],
  );

  // La lista se relee tras cada respuesta de AI Director; el abierto, solo si no hay cambios sin guardar.
  const live = useRef({ selected, dirty });
  useEffect(() => {
    live.current = { selected, dirty };
  });
  useEffect(() => {
    studio.documents(projectId).then(
      (r) => {
        setDocs(r.documents);
        const cur = live.current.selected;
        const target = cur && r.documents.some((d) => d.id === cur) ? cur : (r.documents[0]?.id ?? null);
        if (!target) setSelected(null);
        else if (target !== cur || !live.current.dirty) open(target);
      },
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [projectId, revision, open]);

  async function create() {
    try {
      const d = await studio.createDocument(projectId, { kind: "notes", title: p.untitled, markdown: "" });
      setDocs((list) => [d, ...(list ?? [])]);
      init(d);
      setSelected(d.id);
      setEditing(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(d: ProjectDocSummary) {
    if (!window.confirm(p.confirmDeleteDocument(d.title))) return;
    try {
      await studio.deleteDocument(d.id);
      setDocs((list) => list?.filter((x) => x.id !== d.id) ?? list);
      if (selected === d.id) setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  if (docs === null) return error ? <p className="text-sm text-danger">{error}</p> : <Loader2 className="m-4 size-5 animate-spin text-fg-3" />;
  const current = doc && doc.id === selected ? doc : null;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row">
      <aside className="w-full shrink-0 md:w-64">
        <button
          type="button"
          onClick={() => void create()}
          className="mb-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-line-2 text-sm font-medium text-fg-2 hover:border-lime/50 hover:text-fg"
        >
          <Plus className="size-4" /> {p.newDocument}
        </button>
        {docs.length === 0 && <p className="text-sm text-fg-3">{p.noDocuments}</p>}
        <div className="space-y-1">
          {docs.map((d) => (
            <div key={d.id} className="group relative">
              <button
                type="button"
                onClick={() => open(d.id)}
                className={clsx("flex w-full flex-col items-start rounded-lg px-3 py-2 text-left", selected === d.id ? "bg-surface-4" : "hover:bg-surface-3")}
              >
                <span className="flex w-full items-center gap-1.5 text-sm font-medium text-fg">
                  <FileText className="size-3.5 shrink-0 text-fg-3" />
                  <span className="truncate">{d.title}</span>
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[11px] text-fg-4">
                  {p.kinds[d.kind]} · {p.version(d.version)} ·{" "}
                  {d.updated_by === "agent" ? <Bot className="size-3" /> : <User className="size-3" />}
                  {d.updated_by === "agent" ? p.byAgent : p.byUser}
                </span>
              </button>
              <button
                type="button"
                title={p.deleteDocument}
                aria-label={p.deleteDocument}
                onClick={() => void remove(d)}
                className="absolute top-2 right-2 hidden rounded p-1 text-fg-4 group-hover:block hover:text-danger"
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        {error && <p className="mb-3 rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
        {current && draft && (
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <input
                value={draft.title}
                onChange={(e) => change({ title: e.target.value })}
                maxLength={120}
                aria-label={p.untitled}
                className="h-9 min-w-0 flex-1 rounded-lg border border-line-2 bg-surface-3 px-3 text-[15px] font-semibold outline-none focus:border-lime/50"
              />
              <select
                value={draft.kind}
                onChange={(e) => change({ kind: e.target.value as ProjectDocKind })}
                aria-label={t.cinemaStudio.type}
                className="h-9 rounded-lg bg-surface-3 px-2 text-sm text-fg-2 outline-none"
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {p.kinds[k]}
                  </option>
                ))}
              </select>
              <button type="button" onClick={() => setEditing((v) => !v)} className="flex h-9 items-center gap-1.5 rounded-lg bg-surface-4 px-3 text-sm font-medium text-fg-2 hover:text-fg">
                {editing ? p.preview : <><Pencil className="size-3.5" /> {p.edit}</>}
              </button>
            </div>
            <div className="mb-2 flex items-center gap-2 text-xs text-fg-3">
              <span className={clsx("size-2 rounded-full", state === "saved" ? "bg-success" : state === "conflict" ? "bg-danger" : "bg-warning")} />
              {state === "conflict" ? (
                <>
                  <span className="text-danger">{p.conflict}</span>
                  <button type="button" onClick={() => open(current.id)} className="text-fg-2 underline hover:text-fg">
                    {p.reload}
                  </button>
                </>
              ) : state === "unsaved" ? (
                <button type="button" onClick={() => void retry()} className="text-warning hover:underline">
                  {t.projects.brief.unsaved} · {t.projects.brief.retry}
                </button>
              ) : (
                t.projects.brief[state]
              )}
              <span className="ml-auto">{p.version(current.version)}</span>
            </div>
            {editing ? (
              <textarea
                value={draft.markdown}
                onChange={(e) => change({ markdown: e.target.value })}
                rows={26}
                maxLength={60000}
                className="thin-scrollbar w-full rounded-2xl border border-line-2 bg-surface-2 p-5 font-mono text-[14px] leading-relaxed outline-none focus:border-lime/50"
              />
            ) : (
              <div className="rounded-2xl border border-line bg-surface-2 p-5">
                <Markdown text={draft.markdown || "…"} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
