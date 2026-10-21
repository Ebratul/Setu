"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import { isTypingTarget, OPEN_CHAT_EVENT } from "@/lib/shortcuts";

import { ChatPanel } from "./ChatPanel";
import { ChatSheet } from "./ChatSheet";
import { PromptPathContext } from "./pagePrompts";
import { useChatSession } from "./useChatSession";

/** Deal reference (or uuid) implied by the current page, if any. */
const DEAL_ID = /^[A-Za-z0-9-]{1,64}$/;

export function dealFromRoute(
  pathname: string,
  deal: string | null,
): string | null {
  let candidate: string | null = null;
  const m = /^\/app\/(?:orders|deals)\/([^/]+)/.exec(pathname);
  if (m && m[1] !== "new") {
    try {
      candidate = decodeURIComponent(m[1]);
    } catch {
      return null;
    }
  } else if (pathname.startsWith("/app/financing")) {
    candidate = deal;
  }
  return candidate && DEAL_ID.test(candidate) ? candidate : null;
}

export function ChatDrawer() {
  const t = useT();
  const { lang } = useLang();
  const pathname = usePathname();
  const params = useSearchParams();
  const [open, setOpen] = useState(false);
  const session = useChatSession({ language: lang === "bn" ? "bn" : "en" });
  const { setDeal } = session;
  const routeDeal = dealFromRoute(pathname, params.get("deal"));
  const lastRouteDeal = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (lastRouteDeal.current !== routeDeal) {
      lastRouteDeal.current = routeDeal;
      setDeal(routeDeal);
    }
  }, [routeDeal, setDeal]);

  const onChatPage = pathname.startsWith("/app/chat");
  useEffect(() => {
    if (onChatPage) return;
    const openIt = () => setOpen(true);
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      if (isTypingTarget(e.target) || document.querySelector('[aria-modal="true"]')) return;
      e.preventDefault();
      setOpen(true);
    }
    window.addEventListener(OPEN_CHAT_EVENT, openIt);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(OPEN_CHAT_EVENT, openIt);
      document.removeEventListener("keydown", onKey);
    };
  }, [onChatPage]);

  if (onChatPage) return null;

  const full = session.threadId
    ? `/app/chat?thread=${encodeURIComponent(session.threadId)}`
    : "/app/chat";

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className="fixed right-4 bottom-4 z-40 inline-flex min-h-11 items-center gap-2 rounded-full bg-brand-700 px-5 py-3 text-sm font-semibold text-white shadow-card-hover hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <Icon name="chat" />
        {t("chat.drawer.open")}
      </button>
      {open ? (
        <ChatSheet title={t("chat.drawer.title")} onClose={() => setOpen(false)}>
          <PromptPathContext.Provider value={pathname}>
            <ChatPanel session={session} className="min-h-0 flex-1" />
          </PromptPathContext.Provider>
          <div className="mt-2 flex flex-col gap-2">
            <Link
              href={full}
              onClick={() => setOpen(false)}
              className="inline-flex min-h-11 items-center self-start rounded-md text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              {t("chat.drawer.full")} <span aria-hidden="true">→</span>
            </Link>
          </div>
        </ChatSheet>
      ) : null}
    </>
  );
}
