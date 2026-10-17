"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";

import { ChatCard } from "./cards/ChatCard";
import { Markdown, type CiteCtx } from "./markdown";
import { splitAnswer } from "./messageParts";
import { SourcesList, sourceDomId } from "./SourcesList";
import { ToolChips } from "./ToolChips";
import type { AssistantMessage, UiMessage } from "./types";

type Props = {
  message: UiMessage;
  onRetry: (id: string) => void;
  onRate: (m: AssistantMessage, rating: "up" | "down") => void;
};

const focusRing =
  "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function MessageBubble({ message, onRetry, onRate }: Props) {
  if (message.role === "user") {
    return (
      <li className="flex justify-end">
        <p
          data-role="user"
          className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-700 px-3.5 py-2 text-sm break-words whitespace-pre-wrap text-white"
        >
          {message.text}
        </p>
      </li>
    );
  }
  return <AssistantBubble m={message} onRetry={onRetry} onRate={onRate} />;
}

function AssistantBubble({
  m,
  onRetry,
  onRate,
}: {
  m: AssistantMessage;
  onRetry: Props["onRetry"];
  onRate: Props["onRate"];
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const idPrefix = `cite-${m.id}`;
  const visibleCards = m.cards.filter((c) => c.card_type !== "citations");
  const withheld = m.cards.some(
    (c) => c.card_type === "citations" && c.data.withheld.length > 0,
  );
  const cites: CiteCtx | undefined =
    m.citations.length > 0
      ? {
          citations: new Map(m.citations.map((c) => [c.cite_id, c])),
          onCite: (id) => {
            setHighlight(id);
            const el = document.getElementById(sourceDomId(idPrefix, id));
            el?.scrollIntoView?.({ block: "nearest" });
            el?.focus();
          },
        }
      : undefined;
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const streaming = m.status === "streaming";
  const parts = streaming
    ? { body: m.text, why: null, notes: [], simulated: visibleCards.length > 0 }
    : splitAnswer(m.text, m.why, m.notes, visibleCards);
  const waiting = streaming && m.text === "";
  const interrupted = m.status === "interrupted";
  const canRetry = (m.status === "error" || interrupted) && m.retryText;

  async function copy() {
    try {
      await navigator.clipboard.writeText(m.text);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <li className="flex min-w-0 justify-start">
      <div
        data-role="assistant"
        data-status={m.status}
        className="w-full min-w-0 max-w-full space-y-2 rounded-2xl rounded-bl-md border border-line bg-surface px-3.5 py-3 text-sm text-ink shadow-card sm:max-w-[92%]"
      >
        <ToolChips
          tools={streaming ? m.tools : m.tools.filter((s) => s.status === "error")}
        />
        {waiting ? (
          <p
            role="status"
            data-testid="typing"
            className="flex items-center gap-1 text-muted"
          >
            <span className="sr-only">{t("chat.typing")}</span>
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                aria-hidden="true"
                className="h-2 w-2 animate-pulse rounded-full bg-muted"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </p>
        ) : null}
        {parts.body ? <Markdown text={parts.body} cites={cites} /> : null}
        {parts.why ? (
          <p className="rounded-md border-l-4 border-brand-600 bg-brand-50 px-3 py-1.5 text-sm break-words text-ink">
            {parts.why}
          </p>
        ) : null}
        {visibleCards.length > 0 ? (
          <div className="space-y-3">
            {visibleCards.map((c, i) => (
              <ChatCard key={`${c.card_type}-${i}`} card={c} />
            ))}
          </div>
        ) : null}
        {!streaming && m.citations.length > 0 ? (
          <SourcesList
            citations={m.citations}
            idPrefix={idPrefix}
            highlighted={highlight}
          />
        ) : null}
        {!streaming && withheld ? (
          <p role="note" data-testid="withheld" className="text-xs font-semibold text-warning">
            <span aria-hidden="true">▲ </span>
            {t("chat.sources.withheld")}
          </p>
        ) : null}
        {parts.notes.length > 0 ? (
          <div className="space-y-0.5 text-xs text-muted">
            {parts.notes.map((n) => (
              <Markdown key={n} text={n} />
            ))}
          </div>
        ) : null}
        {parts.simulated && !streaming ? (
          <Badge tone="warning" icon="◇">
            {t("common.simulatedData")}
          </Badge>
        ) : null}
        {m.stopped === "budget" ||
        m.stopped === "tool_cap" ||
        m.stopped === "model_error" ? (
          <p className="text-xs text-warning">{t(`chat.stopped.${m.stopped}`)}</p>
        ) : null}
        {m.status === "aborted" ? (
          <p className="text-xs text-muted">{t("chat.stoppedByUser")}</p>
        ) : null}
        {interrupted ? (
          <p className="text-xs text-warning">{t("chat.interrupted")}</p>
        ) : null}
        {m.status === "error" ? (
          <p role="alert" className="text-sm text-danger">
            {t("chat.error")}
            {m.error ? <span className="block text-xs">{m.error}</span> : null}
          </p>
        ) : null}
        {canRetry ? (
          <Button variant="secondary" onClick={() => onRetry(m.id)}>
            {t("common.retry")}
          </Button>
        ) : null}
        {m.status === "done" && m.text ? (
          <div className="flex flex-wrap items-center gap-1 border-t border-line pt-2">
            <button
              type="button"
              onClick={copy}
              className={`rounded-lg px-2 py-1 text-xs font-semibold text-muted hover:bg-surface-alt ${focusRing}`}
            >
              {copied ? t("chat.copied") : t("chat.copy")}
            </button>
            {m.messageId ? (
              <>
                <button
                  type="button"
                  aria-label={t("chat.feedback.up")}
                  aria-pressed={m.feedback === "up"}
                  onClick={() => onRate(m, "up")}
                  className={`rounded-lg px-2 py-1 text-sm ${focusRing} ${m.feedback === "up" ? "bg-success-soft ring-1 ring-success" : "hover:bg-surface-alt"}`}
                >
                  <span aria-hidden="true">👍</span>
                </button>
                <button
                  type="button"
                  aria-label={t("chat.feedback.down")}
                  aria-pressed={m.feedback === "down"}
                  onClick={() => onRate(m, "down")}
                  className={`rounded-lg px-2 py-1 text-sm ${focusRing} ${m.feedback === "down" ? "bg-danger-soft ring-1 ring-danger" : "hover:bg-surface-alt"}`}
                >
                  <span aria-hidden="true">👎</span>
                </button>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}
