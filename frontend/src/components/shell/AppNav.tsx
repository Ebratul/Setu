"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect } from "react";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { APPROVALS_CHANGED, listApprovals } from "@/lib/api/approvals";
import { getMe } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";
import { usePoll } from "@/lib/usePoll";

import { isCurrent, navGroups } from "./navItems";

type Props = { collapsed?: boolean; onNavigate?: () => void };

/** Role-aware grouped navigation. Collapsed mode keeps names for screen readers and shows them as tooltips. */
export function AppNav({ collapsed = false, onNavigate }: Props) {
  const t = useT();
  const pathname = usePathname();
  const me = useApi((s) => getMe(s), "me");
  const groups = navGroups(me.data?.role);
  const pending = useApi((s) => listApprovals("pending", s), "nav-pending", Boolean(me.data));
  const { reload } = pending;
  const refresh = useCallback(() => reload(), [reload]);
  useEffect(() => {
    window.addEventListener(APPROVALS_CHANGED, refresh);
    return () => window.removeEventListener(APPROVALS_CHANGED, refresh);
  }, [refresh]);
  usePoll(refresh, 20000, Boolean(me.data));
  const count = pending.data?.pending_count ?? 0;
  return (
    <nav aria-label={t("nav.label")} className="space-y-4">
      {groups.map((g) => (
        <div key={g.id}>
          <p
            className={`px-3 pb-1 text-xs font-bold tracking-wide text-muted uppercase ${collapsed ? "sr-only" : ""}`}
          >
            {t(g.labelKey)}
          </p>
          <ul className="space-y-1">
            {g.items.map((item) => {
              const active = isCurrent(item, pathname);
              const label = t(item.key);
              return (
                <li key={`${g.id}-${item.key}`}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    title={collapsed ? label : undefined}
                    onClick={onNavigate}
                    className={`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 text-sm leading-snug font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                      collapsed ? "justify-center" : ""
                    } ${active ? "bg-brand-700 text-white" : "text-ink hover:bg-brand-50"}`}
                  >
                    <Icon name={item.icon} className="shrink-0" />
                    <span className={collapsed ? "sr-only" : "min-w-0 flex-1 break-words"}>{label}</span>
                    {item.href === "/app/approvals" && count > 0 ? (
                      <span
                        data-testid="nav-pending-count"
                        aria-label={t("appr.pendingCount", { n: count })}
                        className="rounded-full bg-danger px-1.5 text-xs font-bold text-white"
                      >
                        {count}
                      </span>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
