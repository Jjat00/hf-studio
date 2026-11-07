"use client";

import clsx from "clsx";
import {
  ArrowUp,
  Check,
  ChevronsRight,
  CornerDownRight,
  FileText,
  Film,
  Hand,
  History,
  ImageIcon,
  Loader2,
  Music,
  Paperclip,
  Plus,
  SlidersHorizontal,
  Square,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Lightbox, type Viewable } from "@/components/lightbox";
import { Logo } from "@/components/logo";
import { CreationsPicker } from "@/components/studio/creations-picker";
import {
  apiSrc,
  formatUsd,
  studio,
  StudioError,
  type Chat,
  type ChatEvent,
  type ChatMessage,
  type ChatMode,
  type ChatPart,
  type ChatQuestion,
  type SkillSummary,
} from "@/lib/studio";
import { useActiveProject } from "@/lib/project";
import type { Generation, ProjectSummary, StudioElement } from "@/lib/types";
import { citedRefs, collectChatMedia, mediaName, MENTION, type ChatMedia } from "./chat-media";
import { ElementProposalCard } from "./element-card";
import { ChatAutoContext, ProposalCard, type ChatAuto } from "./proposal-card";

type Attachment = { url: string; content_type: string; filename: string };
type Draft = { parts: ChatPart[]; status: string | null };

/** Negritas y `código` dentro de una línea. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((piece, i) =>
    piece.startsWith("**") && piece.endsWith("**") ? (
      <strong key={i} className="font-semibold text-fg">
        {piece.slice(2, -2)}
      </strong>
    ) : piece.startsWith("`") && piece.endsWith("`") ? (
      <code key={i} className="rounded bg-surface-4 px-1 py-0.5 font-mono text-[0.9em]">
        {piece.slice(1, -1)}
      </code>
    ) : (
      <Fragment key={i}>{piece}</Fragment>
    ),
  );
}

/** Markdown mínimo del agente: párrafos, títulos y listas. */
export function Markdown({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-fg-2">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => /^\s*([-*]|\d+\.)\s/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const Tag = ordered ? "ol" : "ul";
          return (
            <Tag key={i} className={clsx("space-y-1 pl-5", ordered ? "list-decimal" : "list-disc")}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*([-*]|\d+\.)\s/, ""))}</li>
              ))}
            </Tag>
          );
        }
        if (/^#{1,4}\s/.test(block)) {
          return (
            <p key={i} className="font-semibold text-fg">
              {inline(block.replace(/^#{1,4}\s/, ""))}
            </p>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {inline(block)}
          </p>
        );
      })}
    </div>
  );
}

/** Pregunta del agente con respuestas en las que se hace clic, o una propia. Solo la última se puede responder. */
function QuestionCard({ q, onAnswer }: { q: ChatQuestion; onAnswer?: (text: string) => void }) {
  const { t } = useI18n();
  const s = t.supercomputer;
  const [other, setOther] = useState<string | null>(null);
  const active = Boolean(onAnswer);
  return (
    <div className={clsx("rounded-2xl border p-4", active ? "border-lime/40 bg-surface-2" : "border-line bg-surface-2/50")}>
      <p className="text-[15px] font-semibold text-fg">{q.question}</p>
      <div className="mt-3 flex flex-col gap-2">
        {q.options.map((o) => (
          <button
            key={o.label}
            type="button"
            disabled={!active}
            onClick={() => onAnswer?.(o.label)}
            className="rounded-xl border border-line-2 bg-surface-3 px-3 py-2 text-left transition enabled:hover:border-lime/60 enabled:hover:bg-surface-4 disabled:opacity-60"
          >
            <span className="text-sm font-medium text-fg">{o.label}</span>
            {o.detail && <span className="block text-xs text-fg-3">{o.detail}</span>}
          </button>
        ))}
        {active &&
          (other === null ? (
            <button type="button" onClick={() => setOther("")} className="rounded-xl border border-dashed border-line-2 px-3 py-2 text-left text-sm text-fg-3 hover:text-fg">
              {s.other}
            </button>
          ) : (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (other.trim()) onAnswer?.(other.trim());
              }}
            >
              <input
                autoFocus
                value={other}
                onChange={(e) => setOther(e.target.value)}
                placeholder={s.otherPlaceholder}
                className="h-10 min-w-0 flex-1 rounded-xl border border-line-2 bg-surface-3 px-3 text-sm text-fg outline-none focus:border-lime/60"
              />
              <button type="submit" disabled={!other.trim()} className="h-10 rounded-xl bg-lime px-3 text-sm font-semibold text-ink disabled:opacity-40">
                {s.answer}
              </button>
            </form>
          ))}
      </div>
    </div>
  );
}

/** Páginas que el agente consultó en internet para esta respuesta. */
function Sources({ sources }: { sources: { url: string; title: string }[] }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-fg-4">{t.supercomputer.sources}</span>
      {sources.map((src) => {
        let host = src.url;
        try {
          host = new URL(src.url).hostname.replace(/^www\./, "");
        } catch {
          /* URL rara: se muestra tal cual */
        }
        return (
          <a
            key={src.url}
            href={src.url}
            target="_blank"
            rel="noreferrer"
            title={src.title}
            className="max-w-56 truncate rounded-md bg-surface-4 px-2 py-0.5 text-fg-2 hover:text-fg"
          >
            {host}
          </a>
        );
      })}
    </div>
  );
}

function Parts({ chatId, parts, onAnswer }: { chatId: string; parts: ChatPart[]; onAnswer?: (text: string) => void }) {
  return (
    <div className="space-y-4">
      {parts.map((p, i) =>
        p.type === "text" ? (
          <Markdown key={i} text={p.text} />
        ) : p.type === "sources" ? (
          <Sources key={`sources-${i}`} sources={p.sources} />
        ) : p.type === "question" ? (
          <QuestionCard key={p.question.id} q={p.question} onAnswer={i === parts.length - 1 ? onAnswer : undefined} />
        ) : p.proposal.kind === "element" ? (
          <ElementProposalCard key={p.proposal.tool_use_id} chatId={chatId} proposal={p.proposal} />
        ) : (
          <ProposalCard key={p.proposal.tool_use_id} chatId={chatId} proposal={p.proposal} />
        ),
      )}
    </div>
  );
}

const isVideo = (url: string, contentType?: string) =>
  contentType ? contentType.startsWith("video/") : /\.(mp4|mov|webm|m4v)(\?|$)/i.test(url);

/** Miniatura de una referencia; al tocarla se abre en grande. */
function Thumb({ url, video, className, onOpen }: { url: string; video: boolean; className?: string; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className={clsx("relative shrink-0 overflow-hidden rounded-lg bg-surface-4 hover:ring-2 hover:ring-lime/50", className)}>
      {video ? (
        <video src={url} className="size-full object-cover" muted playsInline preload="metadata" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt="" className="size-full object-cover" />
      )}
      {video && <Film className="absolute right-1 bottom-1 size-3.5 text-white drop-shadow" />}
    </button>
  );
}

/** El texto del usuario con las citas a medios del chat (@imagen2, @video1) resaltadas. */
function withMentions(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MENTION)) {
    const at = m.index ?? 0;
    if (at > 0 && !/\s/.test(text[at - 1])) continue;
    out.push(text.slice(last, at), <span key={at} className="font-medium text-lime">{m[0]}</span>);
    last = at + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

function UserBubble({ m }: { m: Extract<ChatMessage, { role: "user" }> }) {
  const [open, setOpen] = useState<number | null>(null);
  const items: Viewable[] = m.attachments.map((url) => ({ src: url, kind: isVideo(url) ? "video" : "image" }));
  return (
    <div className="flex flex-col items-end gap-2">
      {m.attachments.length > 0 && (
        <div className="flex flex-wrap justify-end gap-2">
          {items.map((it, i) => (
            <Thumb key={it.src} url={it.src} video={it.kind === "video"} className="h-20 w-28" onOpen={() => setOpen(i)} />
          ))}
        </div>
      )}
      {open !== null && <Lightbox items={items} start={open} onClose={() => setOpen(null)} />}
      {m.documents && m.documents.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5">
          {m.documents.map((d) => (
            <span key={d} className="flex items-center gap-1.5 rounded-lg bg-surface-3 px-2 py-1 text-xs text-fg-2">
              <FileText className="size-3.5 text-fg-3" /> {d}
            </span>
          ))}
        </div>
      )}
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-4 px-4 py-2.5 text-[15px] whitespace-pre-wrap text-fg">{withMentions(m.text)}</p>
    </div>
  );
}

export type ChatPanelProps = {
  /** Chat abierto (null: uno nuevo, que se crea al enviar el primer mensaje). */
  chatId: string | null;
  onChatId: (id: string | null) => void;
  /** Proyecto fijo (AI Director): los chats nuevos van a él y no se elige otro. */
  projectId?: string;
  /** `page`: Supercomputer a pantalla completa. `panel`: columna estrecha al lado del proyecto (AI Director). */
  variant?: "page" | "panel";
  /** Tras cada respuesta (para releer la lista de chats). */
  onActivity?: () => void;
  /** Saludo del chat vacío y sugerencias en las que se hace clic (en `panel`). */
  greeting?: ReactNode;
  suggestions?: string[];
  /** Atajos del chat vacío (en `panel`): escriben su texto en el compositor, p. ej. «/lista-de-tomas ». */
  quickActions?: { label: string; text: string }[];
  quickActionsTitle?: string;
  placeholder?: string;
};

/**
 * Chat con el agente de Supercomputer: aclara la idea, elige el modelo y escribe el prompt de escena. Sus propuestas
 * llegan como tarjetas con precio; solo el clic del usuario en una de ellas genera (o el tope de generación
 * automática que el usuario fijó).
 */
export function ChatPanel({ chatId, onChatId, projectId, variant = "page", onActivity, greeting, suggestions, quickActions, quickActionsTitle, placeholder }: ChatPanelProps) {
  const { t, locale } = useI18n();
  const s = t.supercomputer;
  const panel = variant === "panel";

  const [available, setAvailable] = useState(true);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState<string>("");
  const [chat, setChat] = useState<Chat | null>(null);
  const [pending, setPending] = useState<ChatMessage | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<ChatMode>("ask");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const file = useRef<HTMLInputElement>(null);
  const [historyMenu, setHistoryMenu] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [documents, setDocuments] = useState<{ name: string; content: string }[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const dragDepth = useRef(0); // dragenter/dragleave saltan en cada hijo: se cuenta para no parpadear
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  // Menú de skills: la palabra «/algo» que se está escribiendo (sin la barra) y la opción marcada.
  const [slash, setSlash] = useState<{ query: string; start: number; end: number } | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  // Menú «@»: los medios del chat (@imagen2, @video1) y, en `panel`, los elementos. La palabra «@algo» que se escribe.
  const [elements, setElements] = useState<StudioElement[] | null>(null);
  const [at, setAt] = useState<{ query: string; start: number; end: number } | null>(null);
  const [atIndex, setAtIndex] = useState(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const [picking, setPicking] = useState<"image" | "video" | null>(null);
  const [viewing, setViewing] = useState<number | null>(null);
  const streaming = draft !== null;
  // Proyecto y generación automática: los del chat abierto, o los elegidos para el chat nuevo.
  const active = useActiveProject();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [newProject, setNewProject] = useState<string | null | undefined>(undefined);
  const [newBudget, setNewBudget] = useState<number | null>(null);
  const [budgetDraft, setBudgetDraft] = useState("");
  const [askBudget, setAskBudget] = useState(false);
  const [fresh] = useState(() => new Set<string>()); // propuestas llegadas en esta sesión (mutable a propósito)
  // Generaciones lanzadas desde las propuestas (las de esta sesión aún no vienen en el chat guardado) y su estado.
  const [launched, setLaunched] = useState<Record<string, string[]>>({});
  const [jobs, setJobs] = useState<Record<string, Generation>>({});
  const onJobs = useCallback((proposalId: string, ids: string[], states: Record<string, Generation>) => {
    setLaunched((prev) => (prev[proposalId]?.join() === ids.join() ? prev : { ...prev, [proposalId]: ids }));
    setJobs((prev) => {
      const changed = Object.values(states).filter((g) => prev[g.id]?.status !== g.status || prev[g.id]?.outputs.length !== g.outputs.length);
      return changed.length ? { ...prev, ...Object.fromEntries(changed.map((g) => [g.id, g])) } : prev;
    });
  }, []);
  // Sin chat elegido (chat nuevo) no se muestra ni se reutiliza el anterior.
  const current = chatId && chat?.id === chatId ? chat : null;

  useEffect(() => {
    studio.chats().then(
      (r) => {
        setAvailable(r.available);
        setModels(r.models);
        setModel((m) => m || r.default_model);
      },
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
    studio.skills().then((r) => setSkills(r.skills), () => setSkills([]));
    // Al desmontar (otro chat nuevo, cerrar el panel) se corta la respuesta en curso.
    return () => abort.current?.abort();
  }, []);

  const slashMatches = slash
    ? skills
        .filter((k) => k.slug.includes(slash.query))
        .sort((a, b) => Number(!a.slug.startsWith(slash.query)) - Number(!b.slug.startsWith(slash.query)))
        .slice(0, 8)
    : [];
  const media = useMemo(
    () =>
      collectChatMedia({
        messages: current?.messages ?? [],
        pending,
        draftParts: draft?.parts ?? null,
        composer: attachments,
        launched,
        jobs,
        attachedLabel: s.chatMediaAttached,
        pendingLabel: s.chatMediaPending,
      }),
    [current?.messages, pending, draft?.parts, attachments, launched, jobs, s.chatMediaAttached, s.chatMediaPending],
  );
  // Medios ocultos del menú @ en este chat (repetidos de tanto reintentar): conservan su número, solo no se ofrecen.
  const hiddenKey = `hfs.chat.hidden.${current?.id ?? "new"}`;
  const [hidden, setHidden] = useState<{ key: string; urls: string[] }>({ key: "", urls: [] });
  const hiddenUrls = useMemo(() => {
    if (hidden.key === hiddenKey) return new Set(hidden.urls);
    try {
      return new Set<string>(JSON.parse(window.localStorage.getItem(hiddenKey) ?? "[]") as string[]);
    } catch {
      return new Set<string>();
    }
  }, [hidden, hiddenKey]);
  function hideMedia(url: string) {
    const urls = [...hiddenUrls, url];
    try {
      window.localStorage.setItem(hiddenKey, JSON.stringify(urls));
    } catch {
      /* sin almacenamiento: se oculta solo en esta sesión */
    }
    setHidden({ key: hiddenKey, urls });
  }
  const atQuery = at?.query.toLowerCase() ?? "";
  const mediaMatches: ChatMedia[] = at
    ? media
        .filter((m) => !hiddenUrls.has(m.url))
        .filter((m) => m.ready && [mediaName(m, locale), mediaName(m, locale === "en" ? "es" : "en")].some((n) => n.startsWith(atQuery) || (atQuery && n.includes(atQuery))))
        .slice(-20)
        .reverse() // lo más reciente arriba
    : [];
  const elementMatches = at && panel ? (elements ?? []).filter((el) => el.name.includes(atQuery)).slice(0, 8) : [];
  const atMatches: ({ type: "media"; media: ChatMedia } | { type: "element"; element: StudioElement })[] = [
    ...mediaMatches.map((m) => ({ type: "media" as const, media: m })),
    ...elementMatches.map((el) => ({ type: "element" as const, element: el })),
  ];
  const atWord = (i: number) => {
    const item = atMatches[i] ?? atMatches[0];
    return item.type === "media" ? `@${mediaName(item.media, locale)}` : item.element.mention;
  };

  function updateMenus(value: string, caret: number) {
    const before = value.slice(0, caret);
    const m = /(^|\s)\/([a-z0-9-]*)$/.exec(before);
    if (m) {
      setSlash({ query: m[2], start: caret - m[2].length - 1, end: caret });
      setSlashIndex(0);
    } else setSlash(null);
    const a = /(^|\s)@([\w]*)$/.exec(before);
    if (a) {
      if (panel && elements === null) studio.elements().then((r) => setElements(r.elements), () => setElements([]));
      setAt({ query: a[2], start: caret - a[2].length - 1, end: caret });
      setAtIndex(0);
    } else setAt(null);
  }

  function replaceWord(range: { start: number; end: number }, word: string) {
    const next = `${text.slice(0, range.start)}${word} ${text.slice(range.end)}`;
    const caret = range.start + word.length + 1;
    setText(next);
    setSlash(null);
    setAt(null);
    requestAnimationFrame(() => {
      input.current?.focus();
      input.current?.setSelectionRange(caret, caret);
    });
  }

  // El chat elegido se carga; si ya no existe, se vuelve a un chat nuevo.
  useEffect(() => {
    if (!chatId || chat?.id === chatId) return;
    studio.chat(chatId).then(
      (c) => {
        // Panel ligado a un proyecto (AI Director): un chat que se movió a otro proyecto no se sigue aquí, porque
        // leería otro brief y generaría en otro proyecto. Se empieza uno nuevo.
        if (projectId !== undefined && (c.project_id ?? null) !== projectId) return onChatId(null);
        setChat(c);
        setModel(c.model);
      },
      () => onChatId(null),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [chat?.messages.length, pending, draft]);

  /** Un .md o .txt: si es un SKILL.md se añade a las skills y se llama con /nombre; si no, viaja como documento. */
  async function addText(f: File) {
    const content = await f.text();
    const meta = /^﻿?---\s*\n([\s\S]*?)\n---/.exec(content)?.[1] ?? "";
    const name = /^name:\s*["']?([^"'\n]+)/m.exec(meta)?.[1]?.trim();
    if (name && /^description:/m.test(meta)) {
      const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 63);
      try {
        await studio.createSkill({ skill_md: content });
        setNotice(s.skillImported(slug));
      } catch (e) {
        if (!(e instanceof StudioError && e.code === "skill_exists")) throw e;
        setNotice(s.skillExisting(slug));
      }
      studio.skills().then((r) => setSkills(r.skills), () => undefined);
      setText((t) => (new RegExp(`(^|\\s)/${slug}(\\s|$)`).test(t) ? t : `/${slug} ${t}`));
      return;
    }
    if (content.length > 100_000) throw new Error(s.docTooLong(f.name));
    setDocuments((prev) => {
      if (prev.length >= 3) {
        setError(s.tooManyDocs);
        return prev;
      }
      return prev.some((d) => d.name === f.name) ? prev : [...prev, { name: f.name, content }];
    });
  }

  async function upload(files: FileList | File[] | null) {
    const all = Array.from(files ?? []);
    setNotice(null);
    // Texto (.md, .txt): skill o documento. Lo demás, solo imágenes y videos.
    for (const f of all.filter((x) => /\.(md|markdown|txt)$/i.test(x.name) || x.type === "text/markdown" || x.type === "text/plain")) {
      try {
        await addText(f);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
    const media = all.filter((f) => f.type.startsWith("image/") || f.type.startsWith("video/"));
    if (!media.length) {
      if (file.current) file.current.value = "";
      return;
    }
    setUploading(true);
    try {
      for (const f of media.slice(0, 6 - attachments.length)) {
        const up = await studio.upload(f);
        setAttachments((prev) => [...prev, { url: up.url, content_type: up.content_type, filename: f.name }]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
      if (file.current) file.current.value = "";
    }
  }

  function onEvent(e: ChatEvent) {
    setDraft((d) => {
      if (!d) return d;
      if (e.type === "text") {
        const parts = [...d.parts];
        const last = parts[parts.length - 1];
        if (last?.type === "text") parts[parts.length - 1] = { type: "text", text: last.text + e.text };
        else parts.push({ type: "text", text: e.text });
        return { parts, status: null };
      }
      if (e.type === "tool") return { ...d, status: s.tools[e.label as keyof typeof s.tools] ?? s.thinking };
      if (e.type === "proposal") {
        fresh.add(e.proposal.tool_use_id);
        return { parts: [...d.parts, { type: "proposal", proposal: e.proposal }], status: null };
      }
      if (e.type === "question") return { parts: [...d.parts, { type: "question", question: e.question }], status: null };
      return d;
    });
    if (e.type === "usage") setCost(e.cost_usd);
    if (e.type === "error") setError(e.message);
    if (e.type === "done") {
      setChat(e.chat);
      setPending(null);
      setDraft(null);
    }
  }

  async function send(value = text) {
    const body = value.trim();
    if (!body || streaming || uploading) return;
    setError(null);
    setText("");
    const sent = attachments;
    const docs = documents;
    const refs = citedRefs(body, media); // con la numeración que el usuario ve ahora mismo
    setAttachments([]);
    setDocuments([]);
    setNotice(null);
    setPending({ role: "user", text: body, attachments: sent.map((a) => a.url), attachment_kinds: sent.map((a) => a.content_type.split("/")[0]), documents: docs.map((d) => d.name) });
    setDraft({ parts: [], status: s.thinking });
    setCost(null);
    const controller = new AbortController();
    abort.current = controller;
    let target = current;
    try {
      if (!target) {
        target = await studio.createChat(model || undefined, chatProject);
        if (newBudget) target = { ...target, ...(await studio.updateChat(target.id, { auto_budget_usd: newBudget })) };
        setChat(target);
        onChatId(target.id);
      }
      await studio.sendChat(
        target.id,
        { text: body, mode, model: model || undefined, attachments: sent, documents: docs, ...(refs.length ? { refs } : {}) },
        onEvent,
        controller.signal,
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
    } finally {
      abort.current = null;
      // Si el stream se cortó sin «done», se relee el chat guardado.
      setDraft(null);
      setPending(null);
      if (target) studio.chat(target.id).then(setChat).catch(() => {});
      onActivity?.();
    }
  }

  const messages = current?.messages ?? [];
  const empty = messages.length === 0 && !pending;
  const chatProject = current
    ? (current.project_id ?? null)
    : projectId !== undefined
      ? projectId
      : newProject === undefined
        ? (active?.id ?? null)
        : newProject;
  const budget = current ? (current.auto_budget_usd ?? null) : newBudget;
  const spent = current?.auto_spent_usd ?? 0;
  const left = budget ? Math.max(0, budget - spent) : null;
  const autoValue = useMemo<ChatAuto>(
    () => ({
      projectId: chatProject,
      left,
      fresh,
      onSpent: (spentUsd) => setChat((c) => (c ? { ...c, auto_spent_usd: Math.max(c.auto_spent_usd ?? 0, spentUsd) } : c)),
      onJobs,
    }),
    [chatProject, left, fresh, onJobs],
  );

  useEffect(() => {
    if (optionsOpen && !panel) studio.projects().then((r) => setProjects(r.projects)).catch(() => undefined);
  }, [optionsOpen, panel]);

  async function changeProject(id: string | null) {
    if (!current) return setNewProject(id);
    try {
      const summary = await studio.updateChat(current.id, { project_id: id ?? "" });
      setChat((c) => (c ? { ...c, ...summary } : c));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function changeBudget(value: number | null) {
    setAskBudget(false);
    if (!current) return setNewBudget(value);
    try {
      const summary = await studio.updateChat(current.id, { auto_budget_usd: value ?? 0 });
      setChat((c) => (c ? { ...c, ...summary } : c));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  const totalCost = cost != null ? (current?.cost_usd ?? 0) + cost : current?.cost_usd;

  const budgetForm = (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const v = Number(budgetDraft.replace(",", "."));
        if (v > 0) void changeBudget(Math.min(v, 500));
      }}
    >
      <input
        inputMode="decimal"
        autoFocus={panel}
        value={budgetDraft}
        onChange={(e) => setBudgetDraft(e.target.value)}
        placeholder={s.autoGenBudget}
        className="h-7 min-w-0 flex-1 rounded-lg bg-surface-4 px-2 text-xs text-fg outline-none"
      />
      <button type="submit" className="h-7 rounded-lg bg-lime px-2.5 text-xs font-semibold text-ink">
        {s.autoGenApply}
      </button>
    </form>
  );

  const modelSelect = models.length > 0 && (
    <select
      value={model}
      onChange={(e) => setModel(e.target.value)}
      className={clsx("h-7 rounded-lg bg-surface-4 px-2 text-xs text-fg-2 outline-none", panel && "w-full")}
      aria-label="Claude"
    >
      {models.map((m) => (
        <option key={m} value={m}>
          {m.replace("claude-", "").replace(/-(\d)-(\d)$/, " $1.$2").replace(/^./, (c) => c.toUpperCase())}
        </option>
      ))}
    </select>
  );

  /** Ajustes del panel (AI Director): modelo de Claude y si genera sin preguntar (con un tope en USD). */
  const panelSettings = (
    <div className="relative">
      <button
        type="button"
        title={s.director.settings}
        aria-label={s.director.settings}
        aria-expanded={optionsOpen}
        onClick={() => setOptionsOpen((o) => !o)}
        className={clsx(
          "flex h-8 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium",
          left != null ? "bg-lime/15 text-lime" : "bg-surface-4 text-fg-2 hover:text-fg",
        )}
      >
        <SlidersHorizontal className="size-3.5" />
        {left != null && <span>{formatUsd(left)}</span>}
      </button>
      {optionsOpen && (
        <div className="absolute right-0 bottom-10 z-20 w-72 space-y-3 rounded-xl border border-line-2 bg-surface-2 p-3 shadow-xl">
          <label className="block space-y-1">
            <span className="text-xs font-semibold text-fg-3">{s.director.model}</span>
            {modelSelect}
          </label>
          <div className="space-y-1 border-t border-line pt-3">
            <p className="text-xs font-semibold text-fg-3">{s.director.allowMode}</p>
            <button
              type="button"
              onClick={() => void changeBudget(null)}
              className={clsx("flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left", !budget ? "bg-surface-4" : "hover:bg-surface-3")}
            >
              <Hand className="mt-0.5 size-4 shrink-0 text-fg-2" />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-fg">{s.director.askBefore}</span>
                <span className="block text-xs text-fg-3">{s.director.askBeforeHint}</span>
              </span>
              {!budget && <Check className="size-4 text-lime" />}
            </button>
            <button
              type="button"
              onClick={() => setAskBudget(true)}
              className={clsx("flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left", budget ? "bg-surface-4" : "hover:bg-surface-3")}
            >
              <ChevronsRight className="mt-0.5 size-4 shrink-0 text-fg-2" />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-fg">{s.director.noAsk}</span>
                <span className="block text-xs text-fg-3">{budget ? s.autoGenSpent(formatUsd(spent), formatUsd(budget)) : s.director.noAskHint}</span>
              </span>
              {budget ? <Check className="size-4 text-lime" /> : null}
            </button>
            {askBudget && <div className="px-2 pt-1">{budgetForm}</div>}
          </div>
        </div>
      )}
    </div>
  );

  const pageOptions = (
    <div className="relative">
      <button
        type="button"
        title={s.chatOptions}
        aria-label={s.chatOptions}
        aria-expanded={optionsOpen}
        onClick={() => setOptionsOpen((o) => !o)}
        className={clsx(
          "flex h-7 max-w-44 items-center gap-1 rounded-lg px-2 text-xs font-medium",
          left != null ? "bg-lime/15 text-lime" : "bg-surface-4 text-fg-2 hover:text-fg",
        )}
      >
        <Zap className="size-3.5 shrink-0" />
        <span className="truncate">{left != null ? s.autoGenOn(formatUsd(left)) : (projects.find((x) => x.id === chatProject)?.name ?? (chatProject && active?.id === chatProject ? active.name : s.autoGen))}</span>
      </button>
      {optionsOpen && (
        <div className="absolute bottom-10 left-0 z-20 w-72 space-y-3 rounded-xl border border-line-2 bg-surface-2 p-3 shadow-xl">
          <label className="block space-y-1">
            <span className="text-xs font-semibold text-fg-3">{s.project}</span>
            <select
              value={chatProject ?? ""}
              onChange={(e) => void changeProject(e.target.value || null)}
              className="h-8 w-full rounded-lg bg-surface-4 px-2 text-sm text-fg outline-none"
            >
              <option value="">{s.noProject}</option>
              {chatProject && !projects.some((x) => x.id === chatProject) && (
                <option value={chatProject}>{active?.id === chatProject ? active.name : chatProject}</option>
              )}
              {projects.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </label>
          <div className="space-y-1.5 border-t border-line pt-3">
            <p className="text-xs font-semibold text-fg-3">{budget ? s.autoGenOn(formatUsd(left ?? 0)) : s.autoGenOff}</p>
            <p className="text-xs text-fg-4">{s.autoGenHint}</p>
            {budget ? (
              <div className="flex items-center gap-2">
                <span className="flex-1 text-xs text-fg-2">{s.autoGenSpent(formatUsd(spent), formatUsd(budget))}</span>
                <button type="button" onClick={() => void changeBudget(null)} className="h-7 rounded-lg bg-surface-4 px-2.5 text-xs font-semibold text-fg-2 hover:text-fg">
                  {s.autoGenStop}
                </button>
              </div>
            ) : (
              budgetForm
            )}
          </div>
        </div>
      )}
    </div>
  );

  const composer = (
    <div className="rounded-2xl border border-line-2 bg-surface-2 p-3 shadow-xl focus-within:border-lime/40">
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((a, i) => (
            <span key={a.url} className="relative" title={a.filename}>
              <Thumb url={a.url} video={isVideo(a.url, a.content_type)} className="size-14" onOpen={() => setViewing(i)} />
              <button
                type="button"
                aria-label={s.removeAttachment}
                onClick={() => setAttachments((p) => p.filter((x) => x.url !== a.url))}
                className="absolute -top-1.5 -right-1.5 rounded-full bg-surface-1 p-0.5 text-fg-2 shadow ring-1 ring-line hover:text-fg"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      {(documents.length > 0 || notice) && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {documents.map((d) => (
            <span key={d.name} className="flex items-center gap-1.5 rounded-lg bg-surface-4 py-1 pr-1 pl-2 text-xs text-fg-2">
              <FileText className="size-3.5 text-fg-3" /> {d.name}
              <button
                type="button"
                aria-label={s.removeDocument}
                onClick={() => setDocuments((p) => p.filter((x) => x.name !== d.name))}
                className="rounded p-0.5 hover:bg-surface-5"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          {notice && <span className="flex items-center gap-1.5 text-xs text-lime"><Wand2 className="size-3.5" /> {notice}</span>}
        </div>
      )}
      {viewing !== null && attachments[viewing] && (
        <Lightbox
          items={attachments.map((a) => ({ src: a.url, kind: isVideo(a.url, a.content_type) ? "video" : "image" }))}
          start={viewing}
          onClose={() => setViewing(null)}
        />
      )}
      {picking && (
        <CreationsPicker
          kind={picking}
          max={Math.max(1, 6 - attachments.length)}
          onPick={(url) =>
            setAttachments((prev) =>
              prev.length >= 6 || prev.some((a) => a.url === url)
                ? prev
                : [...prev, { url, content_type: picking === "video" ? "video/mp4" : "image/png", filename: picking === "video" ? s.historyVideo : s.historyImage }],
            )
          }
          onClose={() => setPicking(null)}
        />
      )}
      {slash && (
        <div className="mb-2 overflow-hidden rounded-xl border border-line-2 bg-surface-1">
          <div className="flex items-center justify-between px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">
            {s.skillsMenu}
            <a href="/skills" className="font-normal tracking-normal text-fg-3 normal-case hover:text-fg">
              {s.manageSkills}
            </a>
          </div>
          {slashMatches.length === 0 ? (
            <p className="px-3 pb-2 text-sm text-fg-3">{s.noSkills}</p>
          ) : (
            <ul role="listbox" aria-label={s.skillsMenu}>
              {slashMatches.map((k, i) => (
                <li key={k.slug} role="option" aria-selected={i === slashIndex}>
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => slash && replaceWord(slash, `/${k.slug}`)}
                    onMouseEnter={() => setSlashIndex(i)}
                    className={clsx("flex w-full items-start gap-2 px-3 py-2 text-left", i === slashIndex ? "bg-surface-4" : "hover:bg-surface-3")}
                  >
                    <Wand2 className="mt-0.5 size-4 shrink-0 text-lime" />
                    <span className="min-w-0">
                      <span className="block font-mono text-sm text-fg">/{k.slug}</span>
                      <span className="block truncate text-xs text-fg-3">{k.description}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {at && (
        <div className="thin-scrollbar mb-2 max-h-80 overflow-y-auto rounded-xl border border-line-2 bg-surface-1">
          <ul role="listbox" aria-label={s.chatMediaMenu}>
            <li role="presentation" className="px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">
              {s.chatMediaMenu}
            </li>
            {mediaMatches.length === 0 && (
              <li role="presentation" className="px-3 pb-2 text-sm text-fg-3">
                {s.noChatMedia}
              </li>
            )}
            {mediaMatches.map((m, i) => (
              <li key={`${m.kind}${m.n}`} role="option" aria-selected={i === atIndex}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => at && replaceWord(at, `@${mediaName(m, locale)}`)}
                  onMouseEnter={() => setAtIndex(i)}
                  className={clsx("flex w-full items-center gap-2 px-3 py-1.5 text-left", i === atIndex ? "bg-surface-4" : "hover:bg-surface-3")}
                >
                  <span className="relative size-7 shrink-0 overflow-hidden rounded-md bg-surface-4">
                    {m.kind === "video" ? (
                      <video src={m.src} className="size-full object-cover" muted playsInline preload="metadata" />
                    ) : m.kind === "image" ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={m.src} alt="" className="size-full object-cover" />
                    ) : null}
                    {m.kind === "video" && <Film className="absolute right-0.5 bottom-0.5 size-3 text-white drop-shadow" />}
                    {m.kind === "audio" && <Music className="m-auto mt-1.5 size-4 text-fg-3" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-sm text-fg">@{mediaName(m, locale)}</span>
                    <span className="block truncate text-xs text-fg-3">{m.label}</span>
                  </span>
                  <span
                    role="button"
                    tabIndex={-1}
                    aria-label={s.hideChatMedia}
                    title={s.hideChatMedia}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={(e) => {
                      e.stopPropagation();
                      hideMedia(m.url);
                    }}
                    className="rounded-md p-1 text-fg-4 hover:bg-surface-5 hover:text-fg"
                  >
                    <X className="size-3.5" />
                  </span>
                </button>
              </li>
            ))}
            {panel && (
              <li role="presentation" className="flex items-center justify-between border-t border-line px-3 pt-2 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">
                {s.director.elementsMenu}
                <a href="/elements" className="font-normal tracking-normal text-fg-3 normal-case hover:text-fg">
                  {s.director.manageElements}
                </a>
              </li>
            )}
            {panel && elements === null && (
              <li role="presentation">
                <Loader2 className="mx-3 mb-2 size-4 animate-spin text-fg-3" />
              </li>
            )}
            {panel && elements !== null && elementMatches.length === 0 && (
              <li role="presentation" className="px-3 pb-2 text-sm text-fg-3">
                {s.director.noElements}
              </li>
            )}
            {elementMatches.map((el, j) => {
              const i = mediaMatches.length + j;
              return (
                <li key={el.id} role="option" aria-selected={i === atIndex}>
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => at && replaceWord(at, el.mention)}
                    onMouseEnter={() => setAtIndex(i)}
                    className={clsx("flex w-full items-center gap-2 px-3 py-1.5 text-left", i === atIndex ? "bg-surface-4" : "hover:bg-surface-3")}
                  >
                    {el.images[0] && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={apiSrc(el.images[0])} alt="" className="size-7 shrink-0 rounded-md object-cover" />
                    )}
                    <span className="min-w-0">
                      <span className="block font-mono text-sm text-fg">{el.mention}</span>
                      <span className="block truncate text-xs text-fg-3">{el.description}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <textarea
        ref={input}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          updateMenus(e.target.value, e.target.selectionStart ?? e.target.value.length);
        }}
        onBlur={() => {
          setSlash(null);
          setAt(null);
        }}
        onPaste={(e) => {
          // Pegar una imagen (captura, copiada de la web) la adjunta en vez de pegar texto.
          const files = Array.from(e.clipboardData.files);
          if (files.some((f) => f.type.startsWith("image/") || f.type.startsWith("video/"))) {
            e.preventDefault();
            void upload(files);
          }
        }}
        onKeyDown={(e) => {
          const menu = slash && slashMatches.length > 0 ? "slash" : at && atMatches.length > 0 ? "at" : null;
          if (menu) {
            const size = menu === "slash" ? slashMatches.length : atMatches.length;
            const setIndex = menu === "slash" ? setSlashIndex : setAtIndex;
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              const step = e.key === "ArrowDown" ? 1 : -1;
              setIndex((i) => (i + step + size) % size);
              return;
            }
            if ((e.key === "Enter" || e.key === "Tab") && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (menu === "slash" && slash) replaceWord(slash, `/${(slashMatches[slashIndex] ?? slashMatches[0]).slug}`);
              if (menu === "at" && at) replaceWord(at, atWord(atIndex));
              return;
            }
          }
          if ((slash || at) && e.key === "Escape") {
            e.preventDefault();
            setSlash(null);
            setAt(null);
            return;
          }
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send();
          }
        }}
        rows={empty && !panel ? 3 : 2}
        placeholder={placeholder ?? s.placeholder}
        disabled={!available}
        className="thin-scrollbar max-h-60 w-full resize-none bg-transparent px-1 text-[15px] text-fg outline-none placeholder:text-fg-4"
      />
      <div className="mt-1 flex items-center gap-2">
        <input ref={file} type="file" accept="image/*,video/*,.md,.markdown,.txt" multiple hidden onChange={(e) => upload(e.target.files)} />
        <button
          type="button"
          title={s.attach}
          aria-label={s.attach}
          onClick={() => file.current?.click()}
          disabled={uploading || attachments.length >= 6}
          className="flex size-8 items-center justify-center rounded-full bg-surface-4 text-fg-2 hover:text-fg disabled:opacity-50"
        >
          {uploading ? <Loader2 className="size-4 animate-spin" /> : panel ? <Plus className="size-4" /> : <Paperclip className="size-4" />}
        </button>
        <div className="relative">
          <button
            type="button"
            title={s.fromHistory}
            aria-label={s.fromHistory}
            aria-expanded={historyMenu}
            onClick={() => setHistoryMenu((o) => !o)}
            disabled={attachments.length >= 6}
            className="flex size-8 items-center justify-center rounded-full bg-surface-4 text-fg-2 hover:text-fg disabled:opacity-50"
          >
            <History className="size-4" />
          </button>
          {historyMenu && (
            <div className="absolute bottom-10 left-0 z-20 w-44 overflow-hidden rounded-xl border border-line-2 bg-surface-2 py-1 shadow-xl">
              {(["image", "video"] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => {
                    setHistoryMenu(false);
                    setPicking(k);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-fg-2 hover:bg-surface-4 hover:text-fg"
                >
                  {k === "image" ? <ImageIcon className="size-4" /> : <Film className="size-4" />}
                  {k === "image" ? s.historyImage : s.historyVideo}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex rounded-lg bg-surface-4 p-0.5 text-xs font-medium">
          {(["ask", "auto"] as const).map((m) => (
            <button
              key={m}
              type="button"
              title={s.modeHints[m]}
              onClick={() => setMode(m)}
              className={clsx("rounded-md px-2.5 py-1", mode === m ? "bg-surface-1 text-lime" : "text-fg-3 hover:text-fg")}
            >
              {s.modes[m]}
            </button>
          ))}
        </div>
        {!panel && pageOptions}
        {!panel && modelSelect}
        <span className="flex-1" />
        {totalCost != null && totalCost > 0 && <span className={clsx("text-xs text-fg-4", panel ? "hidden" : "hidden sm:inline")}>{s.chatCost(formatUsd(totalCost))}</span>}
        {panel && panelSettings}
        {streaming ? (
          <button type="button" onClick={() => abort.current?.abort()} title={s.stop} aria-label={s.stop} className="flex size-9 items-center justify-center rounded-full bg-surface-5 text-fg">
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => send()}
            disabled={!text.trim() || uploading || !available}
            title={s.send}
            aria-label={s.send}
            className="flex size-9 items-center justify-center rounded-full bg-lime text-ink transition hover:brightness-105 disabled:opacity-40"
          >
            <ArrowUp className="size-4" />
          </button>
        )}
      </div>
    </div>
  );

  const thread = (
    <div className={clsx("flex flex-col gap-6", panel ? "px-4 py-4" : "mx-auto max-w-3xl px-4 py-6")}>
      {messages.map((m, i) =>
        m.role === "user" ? (
          <UserBubble key={i} m={m} />
        ) : (
          <Parts
            key={i}
            chatId={current!.id}
            parts={m.parts}
            onAnswer={i === messages.length - 1 && !pending && !streaming ? (answer) => void send(answer) : undefined}
          />
        ),
      )}
      {pending?.role === "user" && <UserBubble m={pending} />}
      {draft && chat && (
        <div className="space-y-3">
          <ChatAutoContext.Provider value={{ ...autoValue, draft: true }}>
            <Parts chatId={chat.id} parts={draft.parts} />
          </ChatAutoContext.Provider>
          {draft.status && (
            <p className="flex items-center gap-2 text-sm text-fg-3">
              <Loader2 className="size-4 animate-spin text-lime" /> {draft.status}
            </p>
          )}
        </div>
      )}
      {error && <p className="rounded-xl bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      <div ref={bottom} />
    </div>
  );

  let body: ReactNode;
  if (empty && panel) {
    body = (
      <>
        <div className="thin-scrollbar flex min-h-0 flex-1 flex-col justify-center overflow-y-auto px-5 py-6">
          {greeting}
          {suggestions && (
            <ul className="mt-6 space-y-3">
              {suggestions.map((ex) => (
                <li key={ex}>
                  <button
                    type="button"
                    disabled={!available || streaming}
                    onClick={() => void send(ex)}
                    className="flex items-start gap-3 text-left text-[15px] font-medium text-fg-2 hover:text-fg disabled:opacity-50"
                  >
                    <CornerDownRight className="mt-0.5 size-4 shrink-0 text-fg-4" />
                    {ex}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {quickActions && quickActions.length > 0 && (
            <div className="mt-6">
              {quickActionsTitle && <p className="mb-2 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{quickActionsTitle}</p>}
              <div className="flex flex-wrap gap-1.5">
                {quickActions.map((a) => (
                  <button
                    key={a.text}
                    type="button"
                    onClick={() => {
                      setText(a.text);
                      requestAnimationFrame(() => {
                        input.current?.focus();
                        input.current?.setSelectionRange(a.text.length, a.text.length);
                      });
                    }}
                    className="rounded-full border border-line-2 px-2.5 py-1 text-xs text-fg-2 hover:border-lime/40 hover:text-fg"
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {!available && <p className="mt-4 rounded-xl bg-warning/10 p-3 text-sm text-warning">{s.noKey}</p>}
          {error && <p className="mt-4 text-sm text-danger">{error}</p>}
        </div>
        <div className="p-3">{composer}</div>
      </>
    );
  } else if (empty) {
    body = (
      <div className="flex flex-1 flex-col items-center justify-center px-4">
        <div className="w-full max-w-2xl">
          {greeting ?? (
            <div className="mb-6 flex flex-col items-center gap-3 text-center">
              <Logo />
              <h1 className="headline text-[34px] text-fg sm:text-[44px]">{s.hello}</h1>
              <p className="max-w-xl text-fg-3">{s.subtitle}</p>
            </div>
          )}
          {!available && <p className="mb-3 rounded-xl bg-warning/10 p-3 text-sm text-warning">{s.noKey}</p>}
          {composer}
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {(suggestions ?? s.examples).map((ex) => (
              <button key={ex} type="button" onClick={() => setText(ex)} className="rounded-full border border-line-2 px-3 py-1.5 text-[13px] text-fg-3 hover:border-lime/40 hover:text-fg">
                {ex}
              </button>
            ))}
          </div>
          {error && <p className="mt-3 text-center text-sm text-danger">{error}</p>}
        </div>
      </div>
    );
  } else {
    body = (
      <>
        <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto">{thread}</div>
        <div className={panel ? "p-3" : "mx-auto w-full max-w-3xl px-4 pb-4"}>{composer}</div>
      </>
    );
  }

  return (
    <ChatAutoContext.Provider value={autoValue}>
      <div
        className="relative flex min-h-0 min-w-0 flex-1 flex-col"
        onDragEnter={(e) => {
          if (!e.dataTransfer.types.includes("Files")) return;
          e.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) e.preventDefault();
        }}
        onDragLeave={() => {
          dragDepth.current = Math.max(0, dragDepth.current - 1);
          if (dragDepth.current === 0) setDragging(false);
        }}
        onDrop={(e) => {
          if (!e.dataTransfer.files.length) return;
          e.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          if (available) void upload(e.dataTransfer.files);
        }}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-3 z-30 flex items-center justify-center rounded-3xl border-2 border-dashed border-lime/60 bg-surface-1/80 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-2 text-center">
              <Paperclip className="size-7 text-lime" />
              <p className="text-base font-semibold text-fg">{s.dropFiles}</p>
              <p className="text-xs text-fg-3">{s.dropHint}</p>
            </div>
          </div>
        )}
        {body}
      </div>
    </ChatAutoContext.Provider>
  );
}
