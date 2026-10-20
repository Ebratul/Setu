"use client";

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLang, useT } from "@/i18n";
import type { Impact } from "@/lib/api/financing";
import { formatDate, formatDay, formatMoney } from "@/lib/format";

type Props = { impact: Impact; summary: string };

type Point = { on: string; before: number; after: number };

export function ImpactChart({ impact, summary }: Props) {
  const t = useT();
  const { lang } = useLang();
  const cur = impact.currency;
  const data: Point[] = impact.series.map((p) => ({
    on: p.on,
    before: Number(p.before),
    after: Number(p.after),
  }));
  const text = new Map(impact.series.map((p) => [p.on, p]));
  const low = Math.min(0, ...data.map((p) => Math.min(p.before, p.after)));
  const has = (on: string) => text.has(on);
  return (
    <div>
      <div role="img" aria-label={summary} className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            data={data}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
            {low < 0 ? (
              <ReferenceArea
                y1={low}
                y2={0}
                fill="var(--color-danger)"
                fillOpacity={0.12}
                ifOverflow="extendDomain"
              />
            ) : null}
            <XAxis
              dataKey="on"
              tick={{ fontSize: 12 }}
              tickFormatter={(v: string) => formatDay(v, lang)}
              interval="preserveStartEnd"
              minTickGap={32}
            />
            <YAxis tick={{ fontSize: 12 }} width={56} />
            <ReferenceLine
              y={0}
              stroke="var(--color-danger)"
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
            />
            {has(impact.inflow.on) ? (
              <ReferenceLine
                x={impact.inflow.on}
                stroke="var(--color-success)"
                strokeDasharray="2 3"
              />
            ) : null}
            {has(impact.repayment.on) ? (
              <ReferenceLine
                x={impact.repayment.on}
                stroke="var(--color-warning)"
                strokeDasharray="2 3"
              />
            ) : null}
            <Tooltip
              labelFormatter={(v) => formatDate(String(v), lang)}
              formatter={(_v, name, item) => {
                const p = text.get((item.payload as Point).on);
                const raw = name === "after" ? p?.after : p?.before;
                return [
                  formatMoney(raw ?? "0", cur, lang),
                  name === "after" ? t("fin.imp.after") : t("fin.imp.before"),
                ];
              }}
            />
            <Line
              dataKey="before"
              stroke="var(--color-chart-5)"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="after"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <li>
          <span aria-hidden="true" className="text-chart-5">
            ┅
          </span>{" "}
          {t("fin.imp.before")}
        </li>
        <li>
          <span aria-hidden="true" className="text-chart-1">
            ━
          </span>{" "}
          {t("fin.imp.after")}
        </li>
        <li>
          <span aria-hidden="true" className="text-danger">
            ▒
          </span>{" "}
          {t("fin.imp.zone")}
        </li>
        <li>
          <span aria-hidden="true" className="text-success">
            ┊
          </span>{" "}
          {t("fin.imp.inflow")}
        </li>
        <li>
          <span aria-hidden="true" className="text-warning">
            ┊
          </span>{" "}
          {t("fin.imp.repay")}
        </li>
      </ul>
    </div>
  );
}
