"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import {
  deleteThread,
  listThreads,
  renameThread,
  isUuid,
  type ChatThread,
} from "@/lib/api/chat";
import { useApi, useDebounced } from "@/lib/useApi";

import { ChatPanel } from "./ChatPanel";
import { ThreadList } from "./ThreadList";
import { useChatSession } from "./useChatSession";

export function ChatPage() {
  const t = useT();
  const { lang } = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const rawThread = params.get("thread");
  const urlThread = isUuid(rawThread) ? rawThread : null;
  const [query, setQuery] = useState("");
  const q = useDebounced(query, 300);
  const [focusSignal, setFocusSignal] = useState(0);
  const threads = useApi((s) => listThreads(q, s), `threads:${q}`);
  const { reload } = threads;

  const dealSynced = useRef<string | null>(null);
  const badHandled = useRef<string | null>(null);
  const [showList, setShowList] = useState(false);

  const session = useChatSession({
    language: lang === "bn" ? "bn" : "en",
    onThread: (id) => {
      dealSynced.current = id;
      router.replace(`/app/chat?thread=${encodeURIComponent(id)}`, { scroll: false });
    },
    onTurnEnd: reload,
  });
  const { loadThread, reset, threadRef, setDeal } = session;

  useEffect(() => {
    if (urlThread && urlThread !== threadRef.current) {
      void loadThread(urlThread);
      setFocusSignal((n) => n + 1);
    } else if (!urlThread && threadRef.current) {
      reset();
    }
    if (rawThread !== null && urlThread === null && badHandled.current !== rawThread) {
      badHandled.current = rawThread;
      reset();
      router.replace("/app/chat", { scroll: false });
    }
  }, [urlThread, rawThread, loadThread, reset, threadRef, router]);

  const known = threads.data?.threads;
  useEffect(() => {
    const th = known?.find((x) => x.id === urlThread);
    if (th && dealSynced.current !== th.id) {
      dealSynced.current = th.id;
      setDeal(th.deal_id);
    }
  }, [known, urlThread, setDeal]);

  const select = useCallback(
    (th: ChatThread) => {
      router.replace(`/app/chat?thread=${encodeURIComponent(th.id)}`, { scroll: false });
    },
    [router],
  );

  const onNew = () => {
    reset();
    setDeal(null);
    router.replace("/app/chat", { scroll: false });
    setFocusSignal((n) => n + 1);
  };

  async function onRename(id: string, title: string) {
    await renameThread(id, title);
    reload();
  }

  async function onDelete(id: string) {
    await deleteThread(id);
    if (threadRef.current === id) onNew();
    reload();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("chat.title")}</h1>
        <SimulatedBadge />
      </div>
      <div className="grid gap-4 md:grid-cols-[16rem_minmax(0,1fr)]">
        <div className="rounded-card bg-surface p-3 shadow-card">
          <button
            type="button"
            aria-expanded={showList}
            aria-controls="chat-threads"
            onClick={() => setShowList((v) => !v)}
            className="w-full rounded-md text-left text-sm font-bold text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none md:hidden"
          >
            {t("chat.threads.label")} <span aria-hidden="true">{showList ? "▴" : "▾"}</span>
          </button>
          <h2 className="mb-2 hidden text-sm font-bold text-ink md:block">
            {t("chat.threads.label")}
          </h2>
          <div
            id="chat-threads"
            className={`mt-3 md:mt-0 md:block ${showList ? "block" : "hidden"}`}
          >
            <ThreadList
              threads={known ?? []}
              activeId={session.threadId}
              query={query}
              onQuery={setQuery}
              onSelect={select}
              onNew={onNew}
              onRename={onRename}
              onDelete={onDelete}
              loading={threads.loading}
            />
          </div>
        </div>
        <section
          aria-labelledby="chat-conv-h"
          className="flex h-[calc(100dvh-13rem)] min-h-[30rem] min-w-0 flex-col rounded-card bg-surface p-3 shadow-card sm:p-4"
        >
          <h2 id="chat-conv-h" className="sr-only">
            {t("chat.conversation")}
          </h2>
          <ChatPanel session={session} focusSignal={focusSignal} className="flex-1" />
        </section>
      </div>
    </div>
  );
}
