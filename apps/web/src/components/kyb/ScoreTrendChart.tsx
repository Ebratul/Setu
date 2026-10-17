"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLang, useT } from "@/i18n";
import type { SupplierProfile } from "@/lib/api/kyb";
import { formatDecimal, formatMonth } from "@/lib/format";

type Props = { points: SupplierProfile["score_trend"] };

export function ScoreTrendChart({ points }: Props) {
  const t = useT();
  const { lang } = useLang();
  if (points.length === 0) {
    return <p className="text-sm text-muted">{t("sup.trendEmpty")}</p>;
  }
  // plotting coordinates only; displayed numbers are the server strings
  const data = points.map((p) => ({
    month: formatMonth(p.month, lang),
    score: Number(p.score),
  }));
  return (
    <div>
      <div role="img" aria-label={t("sup.trend")} className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 12 }} width={36} />
            <Tooltip formatter={(v) => formatDecimal(String(v), lang, 2)} />
            <Line
              dataKey="score"
              name={t("sup.col.score")}
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer rounded font-semibold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
          {t("sup.trendTable")}
        </summary>
        <table className="mt-2 w-full min-w-60">
          <caption className="sr-only">{t("sup.trendCaption")}</caption>
          <thead>
            <tr className="border-b border-line text-left text-muted">
              <th scope="col" className="py-1 font-medium">{t("sup.month")}</th>
              <th scope="col" className="py-1 text-right font-medium">{t("sup.col.score")}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.month} className="border-b border-line last:border-0">
                <th scope="row" className="py-1 text-left font-medium">
                  {formatMonth(p.month, lang)}
                </th>
                <td className="py-1 text-right tabular-nums">
                  {formatDecimal(p.score, lang, 2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
