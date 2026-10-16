"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/Badge";
import { useLang, useT } from "@/i18n";
import type { AlertPreview, AlertStatus } from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";

import { actionHref } from "./alertUtils";
import { SeverityBadge } from "./SeverityBadge";

export type AlertView = AlertPreview & { id?: string; status?: AlertStatus };

type Props = { alert: AlertView; actions?: ReactNode };

const CURRENCIES: readonly string[] = ["USD", "BDT", "CNY"];
const SHOWS_AMOUNT = new Set(["SHORTFALL", "DEADLINE"]);

export function AlertItem({ alert, actions }: Props) {
  const t = useT();
  const { lang } = useLang();
  const bn = lang === "bn";
  const showAmount =
    SHOWS_AMOUNT.has(alert.type) &&
    alert.amount !== null &&
    alert.currency !== null &&
    CURRENCIES.includes(alert.currency);
  return (
    <li
      data-alert-type={alert.type}
      data-severity={alert.severity}
      className="rounded-xl border border-line bg-surface p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={alert.severity} />
        <Badge>{t(`alertType.${alert.type}`)}</Badge>
        {alert.status ? (
          <Badge tone={alert.status === "RESOLVED" ? "success" : "neutral"}>
            {t(`alertStatus.${alert.status}`)}
          </Badge>
        ) : null}
        {alert.due_on ? (
          <span className="text-xs text-muted">
            {t("alerts.due", { date: formatDate(alert.due_on, lang) })}
          </span>
        ) : null}
      </div>
      <p className="mt-2 font-semibold text-ink">
        {bn ? alert.title_bn : alert.title_en}
      </p>
      {showAmount ? (
        <p
          className="mt-1 text-lg font-bold text-ink tabular-nums"
          aria-label={`${formatMoney(alert.amount ?? "0", alert.currency as Currency, lang)} ${alert.currency}`}
        >
          {formatMoney(alert.amount ?? "0", alert.currency as Currency, lang)}
        </p>
      ) : null}
      <p className="mt-1 text-sm text-muted">
        {bn ? alert.message_bn : alert.message_en}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {alert.action ? (
          <Link
            href={actionHref(alert.action)}
            className="rounded-xl border border-brand-700 px-3 py-1.5 text-sm font-semibold text-brand-700 hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {bn ? alert.action.label_bn : alert.action.label_en}
          </Link>
        ) : null}
        {actions}
      </div>
    </li>
  );
}
