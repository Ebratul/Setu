"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCallback, useEffect } from "react";

import { useT } from "@/i18n";
import { APPROVALS_CHANGED, listApprovals } from "@/lib/api/approvals";
import { getMe } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";
import { usePoll } from "@/lib/usePoll";

const ITEMS = [
  { href: "/app", key: "nav.dashboard", exact: true },
  { href: "/app/deals", key: "nav.orders", exact: false },
  { href: "/app/cashflow", key: "nav.cashflow", exact: false },
  { href: "/app/financing", key: "nav.financing", exact: false },
  { href: "/app/suppliers", key: "nav.suppliers", exact: false },
  { href: "/app/analysis", key: "nav.analysis", exact: false },
  { href: "/app/approvals", key: "nav.approvals", exact: false },
  { href: "/app/inbox/email-check", key: "nav.emailCheck", exact: false },
  { href: "/app/chat", key: "nav.chat", exact: false },
] as const;

const REGISTRY = { href: "/app/admin/registry", key: "nav.registry", exact: false } as const;

const RISK = { href: "/app/admin/risk", key: "nav.risk", exact: false } as const;
const PLAYGROUND = { href: "/demo/risk-playground", key: "nav.playground", exact: false } as const;
const PRIVACY = { href: "/app/admin/privacy", key: "nav.privacy", exact: false } as const;
const PRIVACY_PG = { href: "/demo/privacy-playground", key: "nav.privacyPlayground", exact: false } as const;
const SECURITY = { href: "/app/admin/security", key: "nav.security", exact: false } as const;
const ATTACK = { href: "/demo/attack-console", key: "nav.attackConsole", exact: false } as const;
const AUDIT = { href: "/app/admin/audit", key: "nav.audit", exact: false } as const;
const AUDIT_DEMO = { href: "/demo/audit", key: "nav.auditDemo", exact: false } as const;
const SIMULATOR = { href: "/demo/scam-simulator", key: "nav.simulator", exact: false } as const;

export function AppNav() {
  const t = useT();
  const pathname = usePathname();
  const me = useApi((s) => getMe(s), "me");
  const staff = me.data?.role === "ADMIN" || me.data?.role === "JUDGE";
  const buyerLike = me.data?.role === "BUYER" || staff;
  const items = staff
    ? [...ITEMS, REGISTRY, RISK, PLAYGROUND, PRIVACY, PRIVACY_PG, SECURITY, ATTACK, AUDIT, AUDIT_DEMO, SIMULATOR]
    : buyerLike
      ? [...ITEMS, SIMULATOR]
      : ITEMS;
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
    <nav aria-label={t("nav.label")}>
      <ul className="flex flex-wrap gap-1 md:flex-col">
        {items.map((item) => {
          const current = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`block rounded-xl px-4 py-2 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                  current
                    ? "bg-brand-700 text-white"
                    : "text-ink hover:bg-brand-50"
                }`}
              >
                {t(item.key)}
                {item.href === "/app/approvals" && count > 0 ? (
                  <span
                    data-testid="nav-pending-count"
                    aria-label={t("appr.pendingCount", { n: count })}
                    className="ml-2 rounded-full bg-danger px-1.5 text-xs font-bold text-white"
                  >
                    {count}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
