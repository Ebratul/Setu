"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { PHONE_OPEN, getDemoPhone, type PhoneMessage } from "@/lib/api/approvals";
import { useApi } from "@/lib/useApi";
import { usePoll } from "@/lib/usePoll";

/** Simulated SMS inbox. Renders only when /demo/phone answers 200 (demo mode, buyer or admin). */
export function DemoPhone() {
  const t = useT();
  const me = useApi((s) => getMe(s), "me");
  const eligible = me.data?.role === "BUYER" || me.data?.role === "ADMIN";
  const [available, setAvailable] = useState(false);
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<PhoneMessage[]>([]);
  const [freshId, setFreshId] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "ok" | "fail">("idle");
  const lastId = useRef<string | null | undefined>(undefined);
  const codeRef = useRef<HTMLElement>(null);

  const refresh = useCallback(async () => {
    try {
      const msgs = await getDemoPhone();
      if (msgs === null) {
        setAvailable(false);
        return;
      }
      setAvailable(true);
      setMessages(msgs);
      const newest = msgs[0]?.id ?? null;
      if (lastId.current !== undefined && newest && newest !== lastId.current) {
        setFreshId(newest);
        setCopyState("idle");
      }
      lastId.current = newest;
    } catch {
      /* transient network error: keep the last state */
    }
  }, []);

  useEffect(() => {
    if (!eligible) return;
    const id = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(id);
  }, [eligible, refresh]);
  useEffect(() => {
    const onOpen = () => {
      setOpen(true);
      void refresh();
    };
    window.addEventListener(PHONE_OPEN, onOpen);
    return () => window.removeEventListener(PHONE_OPEN, onOpen);
  }, [refresh]);
  usePoll(() => void refresh(), 2000, eligible && available && open);

  if (!eligible || !available) return null;

  const newest = messages[0];

  async function copy() {
    if (!newest) return;
    try {
      await navigator.clipboard.writeText(newest.code);
      setCopyState("ok");
    } catch {
      try {
        const el = codeRef.current;
        if (el) {
          const range = document.createRange();
          range.selectNodeContents(el);
          const sel = window.getSelection();
          sel?.removeAllRanges();
          sel?.addRange(range);
          setCopyState(document.execCommand("copy") ? "ok" : "fail");
        } else setCopyState("fail");
      } catch {
        setCopyState("fail");
      }
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        data-testid="phone-toggle"
        className="fixed bottom-3 left-3 z-55 flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink shadow-card-hover focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <span aria-hidden="true">📱</span>
        {t("phone.open")}
      </button>
    );
  }

  return (
    <aside
      aria-label={t("phone.title")}
      data-testid="demo-phone"
      className="fixed bottom-3 left-3 z-55 w-64 max-w-[calc(100vw-1.5rem)] rounded-[2rem] border-4 border-ink bg-surface p-3 shadow-card-hover"
    >
      <div className="flex items-center justify-between gap-2 px-1">
        <p className="text-sm font-bold text-ink">
          <span aria-hidden="true">📱 </span>
          {t("phone.title")}
        </p>
        <button
          type="button"
          aria-label={t("phone.close")}
          onClick={() => setOpen(false)}
          className="rounded-lg px-2 py-1 text-lg leading-none text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <p className="px-1 text-xs font-semibold tracking-wide text-warning uppercase">{t("phone.simulated")}</p>
      <div className="mt-2 max-h-64 space-y-2 overflow-y-auto rounded-2xl bg-surface-alt p-2" aria-live="polite">
        {messages.length === 0 ? (
          <p className="p-2 text-xs text-muted">{t("phone.empty")}</p>
        ) : (
          messages.slice(0, 3).map((m, i) => (
            <div
              key={m.id}
              data-testid={i === 0 ? "sms-newest" : "sms-old"}
              className={`rounded-2xl rounded-tl-sm border border-line bg-surface p-2 text-sm text-ink ${m.id === freshId ? "sms-new" : ""}`}
            >
              <p className="text-xs font-semibold text-muted">{t("phone.from")}</p>
              <p className="break-words">{m.body}</p>
              {i === 0 ? (
                <p className="mt-1 text-center">
                  <span className="sr-only">{t("phone.newMessage")}: </span>
                  <strong
                    ref={codeRef}
                    data-testid="sms-code"
                    className="font-mono text-2xl tracking-widest text-ink"
                  >
                    {m.code}
                  </strong>
                </p>
              ) : null}
            </div>
          ))
        )}
      </div>
      {newest ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
          <button
            type="button"
            onClick={copy}
            data-testid="copy-code"
            className="rounded-xl bg-brand-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {copyState === "ok" ? `✓ ${t("phone.copied")}` : t("phone.copy")}
          </button>
          {copyState === "fail" ? <span role="status" className="text-xs text-danger">{t("phone.copyFailed")}</span> : null}
        </div>
      ) : null}
      <p className="mt-2 px-1 text-xs text-muted">{t("phone.note")}</p>
    </aside>
  );
}
