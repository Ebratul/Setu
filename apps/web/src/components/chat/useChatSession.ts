"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  getThreadMessages,
  sendFeedback,
  streamChat,
  type ChatCardData,
  type ChatLanguage,
} from "@/lib/api/chat";

import { rebuildMessages } from "./rebuild";
import type { AssistantMessage, UiMessage } from "./types";

type Options = {
  language: ChatLanguage;
  onThread?: (id: string) => void;
  onTurnEnd?: () => void;
};

export const MAX_ANSWER_CHARS = 100_000;

let counter = 0;
const uid = () => `local-${Date.now()}-${counter++}`;

function emptyAssistant(retryText: string): AssistantMessage {
  return {
    id: uid(),
    role: "assistant",
    text: "",
    why: null,
    notes: [],
    cards: [],
    citations: [],
    tools: [],
    status: "streaming",
    error: null,
    messageId: null,
    feedback: null,
    stopped: null,
    retryText,
  };
}

function sameCard(a: ChatCardData, b: ChatCardData) {
  return a.card_type === b.card_type && JSON.stringify(a.data) === JSON.stringify(b.data);
}

export function useChatSession({ language, onThread, onTurnEnd }: Options) {
  const router = useRouter();
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [threadId, setThreadIdState] = useState<string | null>(null);
  const [deal, setDeal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [announce, setAnnounce] = useState("");
  const threadRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const cbRef = useRef({ onThread, onTurnEnd });
  const messagesRef = useRef<UiMessage[]>([]);
  useEffect(() => {
    cbRef.current = { onThread, onTurnEnd };
    messagesRef.current = messages;
  });

  const setThreadId = useCallback((id: string | null) => {
    threadRef.current = id;
    setThreadIdState(id);
  }, []);

  const patch = useCallback(
    (id: string, fn: (m: AssistantMessage) => AssistantMessage) =>
      setMessages((all) =>
        all.map((m) => (m.id === id && m.role === "assistant" ? fn(m) : m)),
      ),
    [],
  );

  const run = useCallback(
    async (text: string, assistantId: string) => {
      const ac = new AbortController();
      abortRef.current = ac;
      setBusy(true);
      setAnnounce("");
      let finished = false;
      let capped = false;
      let streamed = 0;
      try {
        for await (const ev of streamChat(
          {
            message: text,
            language,
            ...(threadRef.current ? { thread_id: threadRef.current } : {}),
            ...(deal ? { deal_id: deal } : {}),
          },
          ac.signal,
        )) {
          if (ev.type === "meta") {
            if (ev.thread_id && threadRef.current !== ev.thread_id) {
              setThreadId(ev.thread_id);
              cbRef.current.onThread?.(ev.thread_id);
            }
          } else if (ev.type === "tool_start") {
            patch(assistantId, (m) => ({
              ...m,
              tools: [...m.tools, { id: ev.id, name: ev.name, status: "running" }],
            }));
          } else if (ev.type === "tool_end") {
            patch(assistantId, (m) => ({
              ...m,
              tools: m.tools.map((s) =>
                s.id === ev.id ? { ...s, status: ev.ok ? "ok" : "error" } : s,
              ),
              cards:
                ev.card && !m.cards.some((c) => sameCard(c, ev.card!))
                  ? [...m.cards, ev.card]
                  : m.cards,
            }));
          } else if (ev.type === "token") {
            streamed += ev.text.length;
            if (streamed > MAX_ANSWER_CHARS) {
              capped = true;
              ac.abort();
              break;
            }
            patch(assistantId, (m) => ({ ...m, text: m.text + ev.text }));
          } else if (ev.type === "final") {
            finished = true;
            const r = ev.response;
            setThreadId(r.thread_id);
            patch(assistantId, (m) => ({
              ...m,
              text: r.answer,
              why: r.why ?? null,
              notes: r.notes ?? [],
              cards: r.cards && r.cards.length > 0 ? [...r.cards] : m.cards,
              citations: r.citations ?? [],
              messageId: r.message_id,
              stopped: r.stopped ?? null,
              security: r.security ?? null,
              status: "done",
              tools: m.tools.map((s) =>
                s.status === "running" ? { ...s, status: "ok" } : s,
              ),
            }));
            setAnnounce(r.answer);
          } else if (ev.type === "error") {
            finished = true;
            patch(assistantId, (m) => ({
              ...m,
              status: "error",
              error: ev.message || ev.code,
            }));
            setAnnounce(ev.message || ev.code);
          }
        }
        if (capped) {
          patch(assistantId, (m) => ({
            ...m,
            status: "error",
            error: "Response too long",
          }));
        } else if (!finished) {
          patch(assistantId, (m) => ({ ...m, status: "interrupted" }));
        }
      } catch (e) {
        if (ac.signal.aborted && !capped) {
          patch(assistantId, (m) => ({ ...m, status: "aborted" }));
        } else {
          if (e instanceof ApiError && e.status === 401) {
            router.replace(
              `/login?next=${encodeURIComponent(window.location.pathname)}`,
            );
          }
          const msg =
            e instanceof ApiError
              ? (e.detail ?? `HTTP ${e.status}`)
              : e instanceof Error
                ? e.message
                : String(e);
          patch(assistantId, (m) => ({ ...m, status: "error", error: msg }));
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
        cbRef.current.onTurnEnd?.();
      }
    },
    [language, deal, patch, setThreadId, router],
  );

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text || abortRef.current) return;
      const assistant = emptyAssistant(text);
      setMessages((all) => [
        ...all,
        { id: uid(), role: "user", text },
        assistant,
      ]);
      void run(text, assistant.id);
    },
    [run],
  );

  const retry = useCallback(
    (assistantId: string) => {
      if (abortRef.current) return;
      const target = messagesRef.current.find((m) => m.id === assistantId);
      if (!target || target.role !== "assistant" || !target.retryText) return;
      const text = target.retryText;
      setMessages((all) =>
        all.map((m) =>
          m.id === assistantId ? { ...emptyAssistant(text), id: m.id } : m,
        ),
      );
      void run(text, assistantId);
    },
    [run],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setThreadId(null);
    setLoadError(null);
    setAnnounce("");
  }, [setThreadId]);

  const loadThread = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      setThreadId(id);
      setLoading(true);
      setLoadError(null);
      try {
        const res = await getThreadMessages(id);
        if (threadRef.current !== id) return;
        setMessages(rebuildMessages(res.messages));
      } catch (e) {
        if (threadRef.current === id) {
          setMessages([]);
          setLoadError(e);
        }
      } finally {
        if (threadRef.current === id) setLoading(false);
      }
    },
    [setThreadId],
  );

  const rate = useCallback(
    async (m: AssistantMessage, rating: "up" | "down") => {
      if (!m.messageId) return;
      const prev = m.feedback;
      patch(m.id, (x) => ({ ...x, feedback: rating }));
      try {
        await sendFeedback(m.messageId, rating);
      } catch {
        patch(m.id, (x) => ({ ...x, feedback: prev }));
      }
    },
    [patch],
  );

  useEffect(() => () => abortRef.current?.abort(), []);

  return {
    messages,
    threadId,
    threadRef,
    deal,
    setDeal,
    busy,
    loading,
    loadError,
    announce,
    send,
    retry,
    stop,
    reset,
    loadThread,
    rate,
  };
}

export type ChatSession = ReturnType<typeof useChatSession>;
