"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import type { Dashboard } from "@/lib/api/cashflow";
import { formatMonth, formatMoney, formatPct } from "@/lib/format";

type Props = { month: Dashboard["month"]; currency: Currency };

export function MonthCard({ month, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  const rows: [string, string][] = [
    [t("monthly.kpi.deals"), String(month.deals_count)],
    [
      t("monthly.kpi.purchases"),
      formatMoney(month.total_purchases[currency], currency, lang),
    ],
    [
      t("monthly.kpi.landed"),
      formatMoney(month.total_landed_cost[currency], currency, lang),
    ],
    [
      t("monthly.kpi.margin"),
      month.average_margin_pct
        ? formatPct(month.average_margin_pct, lang)
        : "—",
    ],
  ];
  return (
    <Card as="section" labelledBy="month-h">
      <h2 id="month-h" className="text-lg font-semibold text-ink">
        {t("dash.month", { month: formatMonth(month.month, lang) })}
      </h2>
      <dl className="mt-3 space-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-muted">{k}</dt>
            <dd className="font-semibold text-ink tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <Link
        href="/app/analysis?tab=monthly"
        className="mt-3 inline-block font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        {t("dash.monthLink")}
      </Link>
    </Card>
  );
}
