"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import type { Currency, OrderAnalysis } from "@/lib/api/analysis";
import { formatMoney, formatPct } from "@/lib/format";

import { Money } from "./Money";

const COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
  "var(--color-chart-6)",
];

type Props = { data: OrderAnalysis; currency: Currency };

export function CostBreakdown({ data, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  const rows = data.breakdown.map((line, i) => ({
    key: `${line.kind}-${i}`,
    name:
      line.kind === "OTHER" && line.label ? line.label : t(`kind.${line.kind}`),
    note: line.kind === "OTHER" ? null : line.label,
    // plotting only: the number is a chart coordinate, never shown or summed
    plot: Number(line.amount[currency]),
    line,
    color: COLORS[i % COLORS.length],
  }));
  const chartData = [
    Object.fromEntries([["name", ""], ...rows.map((r) => [r.key, r.plot])]),
  ];

  return (
    <Card as="section" labelledBy="breakdown-h">
      <h2 id="breakdown-h" className="text-lg font-semibold text-ink">
        {t("analysis.breakdown.title")}
      </h2>
      <div
        role="img"
        aria-label={t("analysis.breakdown.chartLabel")}
        className="mt-3 h-24 w-full"
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
          >
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" hide />
            <Tooltip
              formatter={(v, name) => [
                formatMoney(String(v), currency, lang),
                String(name),
              ]}
            />
            {rows.map((r) => (
              <Bar
                key={r.key}
                dataKey={r.key}
                name={r.name}
                stackId="cost"
                fill={r.color}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-72 text-sm">
          <caption className="sr-only">
            {t("analysis.breakdown.caption", { currency })}
          </caption>
          <thead>
            <tr className="border-b border-line text-left text-muted">
              <th scope="col" className="py-2 font-medium">
                {t("analysis.breakdown.item")}
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">
                {t("analysis.breakdown.amount")}
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">
                {t("analysis.breakdown.share")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-line last:border-0">
                <th scope="row" className="py-2 text-left font-medium text-ink">
                  <span
                    aria-hidden="true"
                    className="mr-2 inline-block size-3 rounded-sm align-middle"
                    style={{ background: r.color }}
                  />
                  {r.name}
                  {r.note && (
                    <span className="block pl-5 text-xs font-normal text-muted">
                      {r.note}
                    </span>
                  )}
                </th>
                <td className="py-2 pl-3 text-right whitespace-nowrap tabular-nums">
                  <Money amounts={r.line.amount} currency={currency} />
                </td>
                <td className="py-2 pl-3 text-right whitespace-nowrap tabular-nums">
                  {formatPct(r.line.share_pct, lang)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-ink font-semibold">
              <th scope="row" className="py-2 text-left">
                {t("analysis.kpi.landedCost")}
              </th>
              <td className="py-2 pl-3 text-right whitespace-nowrap tabular-nums">
                <Money amounts={data.landed_cost} currency={currency} />
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}
