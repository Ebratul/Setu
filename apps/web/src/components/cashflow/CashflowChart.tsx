"use client";

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useLang, useT } from "@/i18n";
import type { Forecast } from "@/lib/api/cashflow";
import {
  formatDate,
  formatDay,
  formatMoney,
  type Currency,
} from "@/lib/format";

import {
  buildChartPoints,
  shortfallRanges,
  type ChartPoint,
} from "./chartData";

type Props = { forecast: Forecast; compact?: boolean };

type DotProps = { cx?: number; cy?: number; payload?: ChartPoint };

export function CashflowChart({ forecast, compact = false }: Props) {
  const t = useT();
  const { lang } = useLang();
  const cur = forecast.currency as Currency;
  const points = buildChartPoints(forecast);
  const ranges = shortfallRanges(points);
  const money = (v: string) => formatMoney(v, cur, lang);
  const shortfall = forecast.first_shortfall;
  const shortfallPoint = shortfall
    ? points.find((p) => p.on === shortfall.on)
    : undefined;
  const hasZone = Number(forecast.lowest_balance) < Number(forecast.min_buffer);

  const summary = shortfall
    ? t("cf.chartSummaryShortfall", {
        start: formatDate(forecast.start, lang),
        end: formatDate(forecast.end, lang),
        opening: money(forecast.opening_balance),
        date: formatDate(shortfall.on, lang),
        amount: money(shortfall.amount),
        lowest: money(forecast.lowest_balance),
        lowestOn: formatDate(forecast.lowest_on, lang),
      })
    : t("cf.chartSummaryOk", {
        start: formatDate(forecast.start, lang),
        end: formatDate(forecast.end, lang),
        opening: money(forecast.opening_balance),
        lowest: money(forecast.lowest_balance),
        lowestOn: formatDate(forecast.lowest_on, lang),
      });

  function renderDot(props: DotProps) {
    const { cx, cy, payload } = props;
    if (!payload || cx === undefined || cy === undefined) {
      return <g key={payload?.on ?? "none"} />;
    }
    if (payload.below && !compact) {
      return (
        <rect
          key={payload.on}
          x={cx - 3}
          y={cy - 3}
          width={6}
          height={6}
          fill="var(--color-danger)"
        />
      );
    }
    if (payload.cost && !compact) {
      return (
        <path
          key={payload.on}
          d={`M${cx} ${cy - 5} L${cx + 5} ${cy} L${cx} ${cy + 5} L${cx - 5} ${cy} Z`}
          fill="var(--color-chart-2)"
          stroke="var(--color-surface)"
        />
      );
    }
    return <g key={payload.on} />;
  }

  return (
    <div>
      <div
        role="img"
        aria-label={summary}
        className={compact ? "h-52 w-full" : "h-80 w-full"}
      >
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            data={points}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
            {ranges.map((r) => (
              <ReferenceArea
                key={r.x1}
                x1={r.x1}
                x2={r.x2}
                fill="var(--color-danger)"
                fillOpacity={0.14}
                ifOverflow="extendDomain"
              />
            ))}
            {hasZone ? (
              <ReferenceArea
                y1={Number(forecast.lowest_balance)}
                y2={Number(forecast.min_buffer)}
                fill="var(--color-danger)"
                fillOpacity={0.08}
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
              y={Number(forecast.min_buffer)}
              stroke="var(--color-danger)"
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
            />
            <Tooltip
              labelFormatter={(v) => formatDate(String(v), lang)}
              formatter={(_v, _n, item) => [
                money((item.payload as ChartPoint).closingText),
                t("cf.closing"),
              ]}
            />
            <Line
              dataKey="closing"
              name={t("cf.closing")}
              type="monotone"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={renderDot}
              isAnimationActive={false}
            />
            {shortfallPoint ? (
              <ReferenceDot
                x={shortfallPoint.on}
                y={shortfallPoint.closing}
                r={6}
                fill="var(--color-danger)"
                stroke="var(--color-surface)"
                ifOverflow="extendDomain"
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="sr-only">{summary}</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <li>
          <span aria-hidden="true" className="text-chart-1">
            ━
          </span>{" "}
          {t("cf.legend.balance")}
        </li>
        <li>
          <span aria-hidden="true" className="text-danger">
            ┅
          </span>{" "}
          {t("cf.legend.buffer", { amount: money(forecast.min_buffer) })}
        </li>
        <li>
          <span aria-hidden="true" className="text-danger">
            ▒
          </span>{" "}
          {t("cf.legend.shortfall")}
        </li>
        {!compact ? (
          <li>
            <span aria-hidden="true" className="text-chart-2">
              ◆
            </span>{" "}
            {t("cf.legend.dealCost")}
          </li>
        ) : null}
        {shortfall ? (
          <li>
            <span aria-hidden="true" className="text-danger">
              ●
            </span>{" "}
            {t("cf.legend.firstShortfall", {
              date: formatDate(shortfall.on, lang),
            })}
          </li>
        ) : null}
      </ul>
    </div>
  );
}
