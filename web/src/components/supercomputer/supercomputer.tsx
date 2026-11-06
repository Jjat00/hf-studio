"use client";

import clsx from "clsx";
import { ArrowUp, Loader2, MessageSquare, Paperclip, Plus, Square, Trash2, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "@/components/i18n-provider";
import { Logo } from "@/components/logo";
import {
  formatUsd,
  studio,
  type Chat,
  type ChatEvent,
  type ChatMessage,
  type ChatMode,
  type ChatPart,
  type ChatSummary,
} from "@/lib/studio";
import { ProposalCard } from "./proposal-card";

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
function Markdown({ text }: { text: string }) {
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

function Parts({ chatId, parts }: { chatId: string; parts: ChatPart[] }) {
  return (
    <div className="space-y-4">
      {parts.map((p, i) =>
        p.type === "text" ? (
          <Markdown key={i} text={p.text} />
        ) : (
          <ProposalCard key={p.proposal.tool_use_id} chatId={chatId} proposal={p.proposal} />
        ),
      )}
    </div>
  );
}

function UserBubble({ m }: { m: Extract<ChatMessage, { role: "user" }> }) {
  return (
    <div className="flex flex-col items-end gap-2">
      {m.attachments.length > 0 && (
        <div className="flex flex-wrap justify-end gap-2">
          {m.attachments.map((url) =>
            /\.(mp4|mov|webm)(\?|$)/i.test(url) ? (
              <video key={url} src={url} className="h-20 rounded-lg" muted />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={url} src={url} alt="" className="h-20 rounded-lg object-cover" />
            ),
          )}
        </div>
      )}
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-4 px-4 py-2.5 text-[15px] whitespace-pre-wrap text-fg">{m.text}</p>
    </div>
  );
}

/**
 * Supercomputer: chat con un agente que aclara la idea, elige el modelo y escribe el prompt de escena. Sus
 * propuestas llegan como tarjetas con precio; solo el clic del usuario en una de ellas genera.
 */
export function Supercomputer() {
  const { t } = useI18n();
  const s = t.supercomputer;
  const router = useRouter();
  const params = useSearchParams();
  const chatParam = params.get("c");

  const [chats, setChats] = useState<ChatSummary[] | null>(null);
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
  const streaming = draft !== null;
  // Sin ?c= en la URL (chat nuevo) no se muestra ni se reutiliza el chat anterior.
  const current = chatParam && chat?.id === chatParam ? chat : null;

  const loadList = useCallback(() => {
    studio.chats().then(
      (r) => {
        setChats(r.chats);
        setAvailable(r.available);
        setModels(r.models);
        setModel((m) => m || r.default_model);
      },
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setChats([]);
      },
    );
  }, []);

  useEffect(loadList, [loadList]);

  // El chat abierto vive en la URL (?c=…) para poder volver a él.
  useEffect(() => {
    if (!chatParam || chat?.id === chatParam) return;
    studio.chat(chatParam).then(
      (c) => {
        setChat(c);
        setModel(c.model);
      },
      () => router.replace("/supercomputer"),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatParam]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [chat?.messages.length, pending, draft]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const f of Array.from(files).slice(0, 6 - attachments.length)) {
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
      if (e.type === "proposal") return { parts: [...d.parts, { type: "proposal", proposal: e.proposal }], status: null };
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
    setAttachments([]);
    setPending({ role: "user", text: body, attachments: sent.map((a) => a.url) });
    setDraft({ parts: [], status: s.thinking });
    setCost(null);
    const controller = new AbortController();
    abort.current = controller;
    try {
      let target = current;
      if (!target) {
        target = await studio.createChat(model || undefined);
        setChat(target);
        router.replace(`/supercomputer?c=${target.id}`);
      }
      await studio.sendChat(target.id, { text: body, mode, model: model || undefined, attachments: sent }, onEvent, controller.signal);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
    } finally {
      abort.current = null;
      // Si el stream se cortó sin «done», se relee el chat guardado.
      setDraft(null);
      setPending(null);
      const id = current?.id ?? new URLSearchParams(window.location.search).get("c");
      if (id) studio.chat(id).then(setChat).catch(() => {});
      loadList();
    }
  }

  async function remove(id: string) {
    if (!window.confirm(s.confirmDelete)) return;
    setChats((prev) => prev?.filter((c) => c.id !== id) ?? null);
    await studio.deleteChat(id).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    if (current?.id === id) router.replace("/supercomputer");
  }

  function newChat() {
    abort.current?.abort();
    setChat(null);
    setError(null);
    router.replace("/supercomputer");
  }

  const messages = current?.messages ?? [];
  const empty = messages.length === 0 && !pending;
  const totalCost = cost != null ? (current?.cost_usd ?? 0) + cost : current?.cost_usd;

  const composer = (
    <div className="rounded-2xl border border-line-2 bg-surface-2 p-3 shadow-xl focus-within:border-lime/40">
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((a) => (
            <span key={a.url} className="flex items-center gap-1.5 rounded-lg bg-surface-4 py-1 pr-1 pl-2 text-xs text-fg-2">
              {a.filename}
              <button type="button" onClick={() => setAttachments((p) => p.filter((x) => x.url !== a.url))} className="rounded p-0.5 hover:bg-surface-5">
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send();
          }
        }}
        rows={empty ? 3 : 2}
        placeholder={s.placeholder}
        disabled={!available}
        className="thin-scrollbar max-h-60 w-full resize-none bg-transparent px-1 text-[15px] text-fg outline-none placeholder:text-fg-4"
      />
      <div className="mt-1 flex items-center gap-2">
        <input ref={file} type="file" accept="image/*,video/*" multiple hidden onChange={(e) => upload(e.target.files)} />
        <button
          type="button"
          title={s.attach}
          aria-label={s.attach}
          onClick={() => file.current?.click()}
          disabled={uploading || attachments.length >= 6}
          className="flex size-8 items-center justify-center rounded-full bg-surface-4 text-fg-2 hover:text-fg disabled:opacity-50"
        >
          {uploading ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
        </button>
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
        {models.length > 0 && (
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="h-7 rounded-lg bg-surface-4 px-2 text-xs text-fg-2 outline-none"
            aria-label="Claude"
          >
            {models.map((m) => (
              <option key={m} value={m}>
                {m.replace("claude-", "").replace(/-(\d)-(\d)$/, " $1.$2").replace(/^./, (c) => c.toUpperCase())}
              </option>
            ))}
          </select>
        )}
        <span className="flex-1" />
        {totalCost != null && totalCost > 0 && <span className="hidden text-xs text-fg-4 sm:inline">{s.chatCost(formatUsd(totalCost))}</span>}
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

  return (
    <div className="flex h-[calc(100dvh-3.5rem)]">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line md:flex">
        <div className="p-3">
          <button type="button" onClick={newChat} className="flex w-full items-center gap-2 rounded-xl bg-surface-3 px-3 py-2 text-sm font-medium text-fg hover:bg-surface-4">
            <Plus className="size-4" /> {s.newChat}
          </button>
        </div>
        <p className="px-4 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{s.chats}</p>
        <nav className="thin-scrollbar flex-1 overflow-y-auto px-2 pb-3">
          {chats === null ? (
            <Loader2 className="m-3 size-4 animate-spin text-fg-3" />
          ) : chats.length === 0 ? (
            <p className="px-2 py-1 text-sm text-fg-4">{s.noChats}</p>
          ) : (
            chats.map((c) => (
              <div key={c.id} className={clsx("group flex items-center rounded-lg", current?.id === c.id ? "bg-surface-4" : "hover:bg-surface-3")}>
                <button type="button" onClick={() => router.replace(`/supercomputer?c=${c.id}`)} className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-sm text-fg-2">
                  <MessageSquare className="size-3.5 shrink-0 text-fg-4" />
                  <span className="truncate">{c.title}</span>
                </button>
                <button
                  type="button"
                  onClick={() => remove(c.id)}
                  title={s.deleteChat}
                  aria-label={s.deleteChat}
                  className="mr-1 hidden rounded p-1 text-fg-4 group-hover:block hover:text-danger"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))
          )}
        </nav>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        {empty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4">
            <div className="w-full max-w-2xl">
              <div className="mb-6 flex flex-col items-center gap-3 text-center">
                <Logo />
                <h1 className="headline text-[34px] text-fg sm:text-[44px]">{s.hello}</h1>
                <p className="max-w-xl text-fg-3">{s.subtitle}</p>
              </div>
              {!available && <p className="mb-3 rounded-xl bg-warning/10 p-3 text-sm text-warning">{s.noKey}</p>}
              {composer}
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {s.examples.map((ex) => (
                  <button key={ex} type="button" onClick={() => setText(ex)} className="rounded-full border border-line-2 px-3 py-1.5 text-[13px] text-fg-3 hover:border-lime/40 hover:text-fg">
                    {ex}
                  </button>
                ))}
              </div>
              {error && <p className="mt-3 text-center text-sm text-danger">{error}</p>}
            </div>
          </div>
        ) : (
          <>
            <div className="thin-scrollbar flex-1 overflow-y-auto">
              <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
                {messages.map((m, i) =>
                  m.role === "user" ? <UserBubble key={i} m={m} /> : <Parts key={i} chatId={current!.id} parts={m.parts} />,
                )}
                {pending?.role === "user" && <UserBubble m={pending} />}
                {draft && chat && (
                  <div className="space-y-3">
                    <Parts chatId={chat.id} parts={draft.parts} />
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
            </div>
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
          </>
        )}
      </main>
    </div>
  );
}
