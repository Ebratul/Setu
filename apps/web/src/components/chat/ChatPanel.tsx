"use client";

import { useEffect, useRef } from "react";

import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";

import { Composer } from "./Composer";
import { DealSelect } from "./DealSelect";
import { MessageBubble } from "./MessageBubble";
import { SuggestedQuestions } from "./SuggestedQuestions";
import type { ChatSession } from "./useChatSession";

type Props = {
  session: ChatSession;
  focusSignal?: number;
  className?: string;
};

export function ChatPanel({ session, focusSignal = 0, className = "" }: Props) {
  const t = useT();
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const { messages, busy, loading, loadError } = session;

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const empty = messages.length === 0 && !loading && !loadError;

  return (
    <div className={`flex min-h-0 min-w-0 flex-col gap-3 ${className}`}>
      <DealSelect value={session.deal} onChange={session.setDeal} />
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        role="region"
        aria-label={t("chat.conversation")}
        aria-busy={busy}
        tabIndex={0}
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto rounded-xl bg-surface-alt p-2 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none sm:p-3"
      >
        {loading ? (
          <div className="space-y-3" aria-busy="true">
            <Skeleton className="h-16" />
            <Skeleton className="h-24" />
          </div>
        ) : null}
        {loadError ? <QueryError error={loadError} /> : null}
        {empty ? (
          <div className="space-y-2 p-1">
            <p className="text-sm text-ink">{t("chat.empty")}</p>
            <SuggestedQuestions onPick={session.send} />
          </div>
        ) : null}
        {messages.length > 0 ? (
          <ul className="space-y-3">
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                onRetry={session.retry}
                onRate={session.rate}
              />
            ))}
          </ul>
        ) : null}
      </div>
      <p aria-live="polite" role="status" className="sr-only">
        {session.announce}
      </p>
      <Composer
        busy={busy}
        onSend={session.send}
        onStop={session.stop}
        focusSignal={focusSignal}
      />
      <p className="text-xs text-muted">{t("chat.disclaimer")}</p>
    </div>
  );
}
