"use client";

import Link from "next/link";
import { useState } from "react";

import { CurrencyToggle } from "@/components/analysis/CurrencyToggle";
import { KpiCard } from "@/components/analysis/KpiCard";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import { getDashboard } from "@/lib/api/cashflow";
import { formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { ActiveDeals } from "./ActiveDeals";
import { AlertPanel } from "./AlertPanel";
import { MiniCashflow } from "./MiniCashflow";
import { MonthCard } from "./MonthCard";
import { PendingApprovalsCard } from "./PendingApprovalsCard";

export const linkClass =
  "font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none";

type Props = { partyId?: string };

export function DashboardView({ partyId }: Props) {
  const t = useT();
  const { lang } = useLang();
  const [currency, setCurrency] = useState<Currency>("USD");
  const { data, error, reload } = useApi(
    (s) => getDashboard(partyId, s),
    `dashboard|${partyId ?? ""}`,
  );

  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) {
    return (
      <div aria-busy="true" className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  const money = (a: Record<Currency, string>) =>
    formatMoney(a[currency], currency, lang);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">{data.party_name}</h2>
        <CurrencyToggle value={currency} onChange={setCurrency} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label={t("dash.kpi.cash")} value={money(data.cash_balance)} />
        <KpiCard label={t("dash.kpi.escrow")} value={money(data.in_escrow)} />
        <KpiCard
          label={t("dash.kpi.due30")}
          value={money(data.due_next_30_days)}
        />
        <KpiCard
          label={t("dash.kpi.alerts")}
          value={String(data.open_alerts_count)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card
          as="section"
          labelledBy="dash-alerts-h"
          className="min-w-0 space-y-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="dash-alerts-h" className="text-lg font-semibold text-ink">
              {t("dash.alerts")}
            </h2>
            <Link href="/app/cashflow" className={linkClass}>
              {t("dash.allAlerts")}
            </Link>
          </div>
          <AlertPanel alerts={data.alerts} emptyTitle={t("dash.noAlerts")} />
        </Card>
        <div className="min-w-0 space-y-6">
          <PendingApprovalsCard count={data.pending_approvals} />
          <MonthCard month={data.month} currency={currency} />
        </div>
      </div>

      <MiniCashflow partyId={partyId} />
      <ActiveDeals deals={data.active_deals} currency={currency} />
    </div>
  );
}
