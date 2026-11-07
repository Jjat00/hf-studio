"use client";

import clsx from "clsx";
import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/components/i18n-provider";
import { studio, type ChatSummary } from "@/lib/studio";
import { ChatPanel } from "./chat-panel";

export { Markdown } from "./chat-panel";

/**
 * Supercomputer: chat con un agente que aclara la idea, elige el modelo y escribe el prompt de escena. Sus
 * propuestas llegan como tarjetas con precio; solo el clic del usuario en una de ellas genera. El chat abierto vive
 * en la URL (?c=…) para poder volver a él.
 */
export function Supercomputer() {
  const { t } = useI18n();
  const s = t.supercomputer;
  const router = useRouter();
  const params = useSearchParams();
  const chatParam = params.get("c");
  const [chats, setChats] = useState<ChatSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Un chat nuevo monta el panel de cero (y corta la respuesta en curso del anterior).
  const [session, setSession] = useState(0);

  const loadList = useCallback(() => {
    studio.chats().then(
      (r) => setChats(r.chats),
      (e) => {
        setError(e instanceof Error ? e.message : String(e));
        setChats([]);
      },
    );
  }, []);
  useEffect(loadList, [loadList]);

  const openChat = useCallback((id: string | null) => router.replace(id ? `/supercomputer?c=${id}` : "/supercomputer"), [router]);

  async function remove(id: string) {
    if (!window.confirm(s.confirmDelete)) return;
    setChats((prev) => prev?.filter((c) => c.id !== id) ?? null);
    await studio.deleteChat(id).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    if (chatParam === id) openChat(null);
  }

  function newChat() {
    setSession((n) => n + 1);
    openChat(null);
  }

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
            <p className="px-2 py-1 text-sm text-fg-4">{error ?? s.noChats}</p>
          ) : (
            chats.map((c) => (
              <div key={c.id} className={clsx("group flex items-center rounded-lg", chatParam === c.id ? "bg-surface-4" : "hover:bg-surface-3")}>
                <button type="button" onClick={() => openChat(c.id)} className="flex min-w-0 flex-1 items-center gap-2 px-2 py-2 text-left text-sm text-fg-2">
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
        <ChatPanel key={session} chatId={chatParam} onChatId={openChat} onActivity={loadList} />
      </main>
    </div>
  );
}
