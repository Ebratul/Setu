"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLang, useT } from "@/i18n";
import type { Currency, MonthTotals } from "@/lib/api/analysis";
import { formatMonth, formatMoney, formatPct } from "@/lib/format";

import { Money } from "./Money";

type Props = { history: MonthTotals[]; currency: Currency };

export function HistoryChart({ history, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  // plotting coordinates only; displayed values come from the server strings
  const data = history.map((h) => ({
    month: formatMonth(h.month, lang),
    purchases: Number(h.total_purchases[currency]),
    margin: h.average_margin_pct === null ? null : Number(h.average_margin_pct),
  }));
  return (
    <div>
      <div
        role="img"
        aria-label={t("monthly.chartLabel")}
        className="h-64 w-full"
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="l" tick={{ fontSize: 12 }} width={56} />
            <YAxis
              yAxisId="r"
              orientation="right"
              unit="%"
              tick={{ fontSize: 12 }}
              width={44}
            />
            <Tooltip
              formatter={(v, name) =>
                name === t("monthly.purchases")
                  ? formatMoney(String(v), currency, lang)
                  : formatPct(String(v), lang)
              }
            />
            <Legend />
            <Bar
              yAxisId="l"
              dataKey="purchases"
              name={t("monthly.purchases")}
              fill="var(--color-chart-1)"
              isAnimationActive={false}
            />
            <Line
              yAxisId="r"
              dataKey="margin"
              name={t("monthly.avgMargin")}
              stroke="var(--color-chart-2)"
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer font-semibold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
          {t("monthly.showTable")}
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-72">
            <caption className="sr-only">{t("monthly.tableCaption")}</caption>
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th scope="col" className="py-1 font-medium">
                  {t("monthly.month")}
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  {t("monthly.purchases")}
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  {t("monthly.avgMargin")}
                </th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr
                  key={h.month}
                  className="border-b border-line last:border-0"
                >
                  <th scope="row" className="py-1 text-left font-medium">
                    {formatMonth(h.month, lang)}
                  </th>
                  <td className="py-1 text-right tabular-nums">
                    <Money amounts={h.total_purchases} currency={currency} />
                  </td>
                  <td className="py-1 text-right tabular-nums">
                    {h.average_margin_pct
                      ? formatPct(h.average_margin_pct, lang)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
