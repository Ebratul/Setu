"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { TierBadge } from "@/components/risk/TierBadge";
import { useLang, useT } from "@/i18n";
import {
  APPROVALS_CHANGED,
  getNotifications,
  markNotificationsRead,
  type NotificationEvent,
  type Notifications,
} from "@/lib/api/approvals";
import { usePoll } from "@/lib/usePoll";

type Props = { supplier?: boolean };

function hrefFor(e: NotificationEvent, supplier: boolean): string | null {
  if (supplier) return e.deal_reference ? `/supplier/${encodeURIComponent(e.deal_reference)}` : null;
  if (e.approval_id) return `/app/approvals?focus=${e.approval_id}`;
  return e.deal_reference ? `/app/deals/${encodeURIComponent(e.deal_reference)}` : null;
}

/** Bell with an unread count and a small activity feed; opening it marks everything read. */
export function NotificationBell({ supplier = false }: Props) {
  const t = useT();
  const { lang } = useLang();
  const [data, setData] = useState<Notifications | null>(null);
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await getNotifications());
    } catch {
      /* not allowed or offline: hide the count */
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => void refresh(), 0);
    window.addEventListener(APPROVALS_CHANGED, refresh);
    return () => {
      clearTimeout(id);
      window.removeEventListener(APPROVALS_CHANGED, refresh);
    };
  }, [refresh]);
  usePoll(() => void refresh(), 15000, true);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        btn.current?.focus();
      }
    }
    function onDown(e: MouseEvent) {
      if (!box.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      await refresh();
      try {
        await markNotificationsRead();
        setData((d) => (d ? { ...d, unread: 0 } : d));
      } catch {
        /* keep unread */
      }
    } else {
      void refresh();
    }
  }

  if (!data) return null;
  const unread = data.unread;
  return (
    <div className="relative">
      <button
        ref={btn}
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        aria-controls="bell-panel"
        aria-label={t("bell.label")}
        onClick={toggle}
        data-testid="bell"
        className="relative rounded-xl border border-line bg-surface px-3 py-2 text-base focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <span aria-hidden="true">🔔</span>
        {unread > 0 ? (
          <span
            aria-hidden="true"
            data-testid="bell-count"
            className="absolute -top-1.5 -right-1.5 min-w-5 rounded-full bg-danger px-1 text-center text-xs font-bold text-white"
          >
            {unread}
          </span>
        ) : null}
      </button>
      <span aria-live="polite" className="sr-only">
        {unread > 0 ? t("bell.unread", { n: unread }) : ""}
      </span>
      {open ? (
        <div
          ref={box}
          id="bell-panel"
          role="region"
          aria-label={t("bell.title")}
          className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-card border border-line bg-surface p-3 shadow-card-hover"
        >
          <h2 className="mb-2 text-sm font-bold text-ink">{t("bell.title")}</h2>
          {data.items.length === 0 ? (
            <p className="text-sm text-muted">{t("bell.none")}</p>
          ) : (
            <ul className="max-h-80 space-y-2 overflow-y-auto">
              {data.items.map((e) => {
                const href = hrefFor(e, supplier);
                const title = lang === "bn" ? e.title_bn : e.title_en;
                const detail = lang === "bn" ? e.detail_bn : e.detail_en;
                const body = (
                  <>
                    <span className="flex flex-wrap items-center gap-1">
                      {e.tier > 0 && !supplier ? <TierBadge tier={e.tier} /> : null}
                      {e.unread ? (
                        <span className="rounded-full bg-info-soft px-2 text-xs font-semibold text-info">{t("bell.unreadItem")}</span>
                      ) : null}
                    </span>
                    <span className="block text-sm font-semibold text-ink">{title}</span>
                    {detail ? <span className="block text-xs text-muted">{detail}</span> : null}
                    <span className="block text-xs text-muted">
                      {new Date(e.ts).toLocaleString(lang === "bn" ? "bn-BD" : lang === "zh" ? "zh-CN" : "en-US")}
                    </span>
                  </>
                );
                return (
                  <li key={e.id} className="rounded-xl border border-line p-2">
                    {href ? (
                      <Link
                        href={href}
                        onClick={() => setOpen(false)}
                        className="block rounded-md focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                      >
                        {body}
                      </Link>
                    ) : (
                      body
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
