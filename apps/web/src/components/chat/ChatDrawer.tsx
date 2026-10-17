"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { useLang, useT } from "@/i18n";

import { ChatPanel } from "./ChatPanel";
import { useChatSession } from "./useChatSession";

/** Deal reference (or uuid) implied by the current page, if any. */
const DEAL_ID = /^[A-Za-z0-9-]{1,64}$/;

export function dealFromRoute(
  pathname: string,
  deal: string | null,
): string | null {
  let candidate: string | null = null;
  const m = /^\/app\/orders\/([^/]+)/.exec(pathname);
  if (m) {
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
  const session = useChatSession({ language: lang });
  const { setDeal } = session;
  const routeDeal = dealFromRoute(pathname, params.get("deal"));
  const lastRouteDeal = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (lastRouteDeal.current !== routeDeal) {
      lastRouteDeal.current = routeDeal;
      setDeal(routeDeal);
    }
  }, [routeDeal, setDeal]);

  if (pathname.startsWith("/app/chat")) return null;

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
        className="fixed right-4 bottom-4 z-40 rounded-full bg-brand-700 px-5 py-3 text-sm font-semibold text-white shadow-card-hover hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <span aria-hidden="true">💬 </span>
        {t("chat.drawer.open")}
      </button>
      {open ? (
        <Modal title={t("chat.drawer.title")} onClose={() => setOpen(false)}>
          <div className="flex h-[70dvh] min-h-0 flex-col gap-2">
            <ChatPanel session={session} className="min-h-0 flex-1" />
            <Link
              href={full}
              onClick={() => setOpen(false)}
              className="self-start rounded-md text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              {t("chat.drawer.full")} <span aria-hidden="true">→</span>
            </Link>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
