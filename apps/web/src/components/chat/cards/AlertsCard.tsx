"use client";

import Link from "next/link";

import { SeverityBadge } from "@/components/cashflow/SeverityBadge";
import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import type { Severity } from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";

import { safeAppHref } from "../markdown";
import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "alerts" }>;

const RANK: Record<string, number> = { CRITICAL: 0, WARNING: 1, INFO: 2 };
const asSeverity = (s: string): Severity =>
  s === "CRITICAL" || s === "WARNING" ? s : "INFO";

export function AlertsCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const alerts = [...card.data.alerts].sort((a, b) => {
    const r = (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3);
    if (r !== 0) return r;
    return (a.due_on ?? "9999") < (b.due_on ?? "9999") ? -1 : 1;
  });
  return (
    <CardShell
      type="alerts"
      title={t("chat.card.alerts", { n: card.data.count })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
    >
      {alerts.length === 0 ? (
        <p className="text-sm text-muted">{t("chat.alerts.none")}</p>
      ) : (
        <ul className="space-y-2">
          {alerts.map((a) => {
            const href = safeAppHref(a.route);
            return (
              <li
                key={a.id}
                data-alert-type={a.type}
                className="space-y-1 rounded-xl border border-line p-2.5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={asSeverity(a.severity)} />
                  {a.due_on ? (
                    <span className="text-xs text-muted">
                      {formatDate(a.due_on, lang)}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm font-semibold break-words text-ink">
                  {lang === "bn" ? a.title_bn : a.title_en}
                </p>
                {a.amount && a.currency ? (
                  <p className="text-xs text-muted">
                    {formatMoney(a.amount, a.currency as Currency, lang)}
                  </p>
                ) : null}
                {href ? (
                  <Link
                    href={href}
                    className="inline-block rounded-md text-xs font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                  >
                    {t("chat.alerts.open")} <span aria-hidden="true">→</span>
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </CardShell>
  );
}
