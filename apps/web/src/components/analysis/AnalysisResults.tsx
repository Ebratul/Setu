"use client";

import { useT } from "@/i18n";
import type { Currency, OrderAnalysis } from "@/lib/api/analysis";
import { formatMoney, formatPct } from "@/lib/format";
import { useLang } from "@/i18n";

import { CostBreakdown } from "./CostBreakdown";
import { CurrencyToggle } from "./CurrencyToggle";
import { FxNote } from "./FxNote";
import { KpiCard } from "./KpiCard";
import { TargetPriceHelper } from "./TargetPriceHelper";
import { WhyPanel } from "./WhyPanel";

type Props = {
  data: OrderAnalysis;
  currency: Currency;
  onCurrency: (c: Currency) => void;
  target: {
    value: string;
    error: string | null;
    updating: boolean;
    onChange: (v: string) => void;
  };
  busy?: boolean;
};

export function AnalysisResults({
  data,
  currency,
  onCurrency,
  target,
  busy,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const money = (a: { USD: string; BDT: string; CNY: string }) =>
    formatMoney(a[currency], currency, lang);
  return (
    <div className="space-y-6" aria-busy={busy ? true : undefined}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CurrencyToggle value={currency} onChange={onCurrency} />
        <FxNote fx={data.fx} />
      </div>
      <div
        aria-live="polite"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
      >
        <KpiCard
          label={t("analysis.kpi.landedCost")}
          value={money(data.landed_cost)}
          ariaLabel={`${money(data.landed_cost)} ${currency}`}
        />
        <KpiCard
          label={t("analysis.kpi.costPerUnit")}
          value={money(data.cost_per_unit)}
          ariaLabel={`${money(data.cost_per_unit)} ${currency}`}
          hint={`/ ${data.unit}`}
        />
        <KpiCard
          label={t("analysis.kpi.revenue")}
          value={data.expected_revenue ? money(data.expected_revenue) : "—"}
          hint={data.expected_revenue ? undefined : t("analysis.kpi.noPrice")}
        />
        <KpiCard
          label={t("analysis.kpi.margin")}
          value={
            data.gross_margin_pct ? formatPct(data.gross_margin_pct, lang) : "—"
          }
          band={data.margin_band}
          hint={data.margin_band ? undefined : t("analysis.kpi.noPrice")}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <CostBreakdown data={data} currency={currency} />
        <div className="space-y-6">
          <TargetPriceHelper
            data={data}
            currency={currency}
            value={target.value}
            error={target.error}
            updating={target.updating}
            onChange={target.onChange}
          />
          <WhyPanel explanations={data.explanations} facts={data.facts} />
        </div>
      </div>
    </div>
  );
}
