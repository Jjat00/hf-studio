"use client";

import clsx from "clsx";
import { Clapperboard, ExternalLink, History, Loader2, MessageSquare, SquarePen, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { ChatPanel } from "@/components/supercomputer/chat-panel";
import { studio, type ChatSummary } from "@/lib/studio";

const storeKey = (projectId: string) => `hfs.director.${projectId}`;

function readChat(projectId: string): string | null {
  try {
    return window.localStorage.getItem(storeKey(projectId));
  } catch {
    return null;
  }
}

function writeChat(projectId: string, id: string | null) {
  try {
    if (id) window.localStorage.setItem(storeKey(projectId), id);
    else window.localStorage.removeItem(storeKey(projectId));
  } catch {
    /* sin almacenamiento: se empieza un chat nuevo cada vez */
  }
}

/**
 * AI Director: el agente de Supercomputer en un panel al lado del proyecto. Sus chats van a este proyecto (lee su
 * brief) y se recuerda el último abierto. «Generar sin preguntar» usa la generación automática con tope en USD.
 */
export function DirectorPanel({ projectId, onClose, onActivity }: { projectId: string; onClose: () => void; onActivity?: () => void }) {
  const { t } = useI18n();
  const d = t.supercomputer.director;
  const [chatId, setChatId] = useState<string | null>(() => readChat(projectId));
  const [session, setSession] = useState(0);
  const [history, setHistory] = useState<ChatSummary[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  function open(id: string | null) {
    setChatId(id);
    writeChat(projectId, id);
  }

  function loadHistory() {
    studio.chats().then(
      (r) => setHistory(r.chats.filter((c) => c.project_id === projectId)),
      () => setHistory([]),
    );
  }

  const iconButton = "flex size-8 items-center justify-center rounded-lg text-fg-3 hover:bg-surface-3 hover:text-fg";

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-1">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-line px-3">
        <span className="flex size-8 items-center justify-center rounded-lg bg-surface-4 text-fg-2">
          <Clapperboard className="size-4" />
        </span>
        <p className="flex-1 truncate text-[15px] font-semibold">{d.title}</p>
        <div className="relative">
          <button
            type="button"
            title={d.history}
            aria-label={d.history}
            aria-expanded={showHistory}
            onClick={() => {
              if (!showHistory) loadHistory();
              setShowHistory((s) => !s);
            }}
            className={clsx(iconButton, showHistory && "bg-surface-3 text-fg")}
          >
            <History className="size-4" />
          </button>
          {showHistory && (
            <div className="absolute top-full right-0 z-30 mt-1 w-72 overflow-hidden rounded-xl border border-line-2 bg-surface-2 p-1 shadow-2xl">
              <p className="px-2.5 pt-1.5 pb-1 text-[11px] font-semibold tracking-wider text-fg-4 uppercase">{d.history}</p>
              {history === null ? (
                <Loader2 className="m-2 size-4 animate-spin text-fg-3" />
              ) : history.length === 0 ? (
                <p className="px-2.5 py-2 text-sm text-fg-3">{d.noHistory}</p>
              ) : (
                <div className="thin-scrollbar max-h-72 overflow-y-auto">
                  {history.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => {
                        open(c.id);
                        setShowHistory(false);
                      }}
                      className={clsx("flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm", c.id === chatId ? "bg-surface-4 text-fg" : "text-fg-2 hover:bg-surface-3")}
                    >
                      <MessageSquare className="size-3.5 shrink-0 text-fg-4" />
                      <span className="truncate">{c.title}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          title={d.newChat}
          aria-label={d.newChat}
          onClick={() => {
            open(null);
            setSession((n) => n + 1);
          }}
          className={iconButton}
        >
          <SquarePen className="size-4" />
        </button>
        {chatId && (
          <Link href={`/supercomputer?c=${chatId}`} title={d.openFull} aria-label={d.openFull} className={iconButton}>
            <ExternalLink className="size-4" />
          </Link>
        )}
        <button type="button" title={d.close} aria-label={d.close} onClick={onClose} className={iconButton}>
          <X className="size-4" />
        </button>
      </div>
      <ChatPanel
        key={session}
        variant="panel"
        projectId={projectId}
        chatId={chatId}
        onChatId={open}
        placeholder={d.placeholder}
        suggestions={d.suggestions}
        quickActions={d.skills.map((k) => ({ label: k.label, text: `/${k.slug} ` }))}
        quickActionsTitle={d.skillsTitle}
        onActivity={onActivity}
        greeting={
          <div className="flex items-start gap-3">
            <span className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-lime text-ink">
              <Clapperboard className="size-4" />
            </span>
            <h2 className="text-[26px] leading-tight font-semibold tracking-tight text-fg">{d.greeting}</h2>
          </div>
        }
      />
    </div>
  );
}
