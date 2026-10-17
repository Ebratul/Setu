"use client";

import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import {
  formatDate,
  formatDay,
  formatMoney,
  type Currency,
} from "@/lib/format";

import { CardShell, Kpi } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "cashflow" }>;
type Row = { on: string; before: number; after?: number };

/** Chart coordinates only; every displayed amount stays the server's decimal string. */
function buildRows(card: Card): Row[] {
  const after = new Map(
    (card.data.after?.series ?? []).map((p) => [p.on, Number(p.closing)]),
  );
  return card.data.before.series.map((p) => ({
    on: p.on,
    before: Number(p.closing),
    after: after.get(p.on),
  }));
}

export function CashflowCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const cur = d.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);
  const rows = buildRows(card);
  const hasAfter = Boolean(d.after);
  const shortfall = d.before.first_shortfall;
  const afterShortfall = d.after?.first_shortfall ?? null;
  const shortfallRow = shortfall
    ? rows.find((r) => r.on === shortfall.on)
    : undefined;
  const lowest = Number(d.before.lowest_balance);
  const buffer = Number(d.min_buffer);
  const summary = shortfall
    ? t("chat.cf.summaryShortfall", {
        date: formatDate(shortfall.on, lang),
        amount: money(shortfall.amount),
      })
    : t("chat.cf.summaryOk", {
        lowest: money(d.before.lowest_balance),
        date: formatDate(d.before.lowest_on, lang),
      });

  return (
    <CardShell
      type="cashflow"
      title={t("chat.card.cashflow")}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref={d.cashflow_route}
      linkLabel={t("chat.card.openCashflow")}
    >
      <dl className="grid grid-cols-2 gap-2">
        <Kpi
          label={t("chat.cf.firstShortfall")}
          tone={shortfall ? "danger" : "default"}
          value={
            shortfall ? (
              <>
                <span>{money(shortfall.amount)}</span>
                <span className="block text-xs font-semibold text-muted">
                  {formatDate(shortfall.on, lang)}
                </span>
              </>
            ) : (
              t("chat.cf.noShortfall")
            )
          }
        />
        <Kpi
          label={t("chat.cf.lowest")}
          value={
            <>
              <span>{money(d.before.lowest_balance)}</span>
              <span className="block text-xs font-semibold text-muted">
                {formatDate(d.before.lowest_on, lang)}
              </span>
            </>
          }
        />
        {d.after ? (
          <>
            <Kpi
              label={t("chat.cf.afterShortfall")}
              value={
                afterShortfall
                  ? `${money(afterShortfall.amount)} · ${formatDate(afterShortfall.on, lang)}`
                  : t("chat.cf.noShortfall")
              }
            />
            <Kpi
              label={t("chat.cf.afterLowest")}
              value={money(d.after.lowest_balance)}
            />
          </>
        ) : null}
      </dl>
      {d.scenario_label ? (
        <p className="text-xs font-semibold text-ink">
          {t("chat.cf.scenario", { label: d.scenario_label })}
        </p>
      ) : null}
      <div role="img" aria-label={summary} className="h-44 w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            data={rows}
            margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
            {lowest < buffer ? (
              <ReferenceArea
                y1={lowest}
                y2={buffer}
                fill="var(--color-danger)"
                fillOpacity={0.12}
                ifOverflow="extendDomain"
              />
            ) : null}
            <XAxis
              dataKey="on"
              tick={{ fontSize: 11 }}
              tickFormatter={(v: string) => formatDay(v, lang)}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis tick={{ fontSize: 11 }} width={48} />
            <ReferenceLine
              y={buffer}
              stroke="var(--color-danger)"
              strokeDasharray="5 4"
              ifOverflow="extendDomain"
            />
            <Line
              dataKey="before"
              name={t("chat.cf.before")}
              type="monotone"
              stroke="var(--color-chart-1)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            {hasAfter ? (
              <Line
                dataKey="after"
                name={t("chat.cf.after")}
                type="monotone"
                stroke="var(--color-chart-3)"
                strokeWidth={2}
                strokeDasharray="6 3"
                dot={false}
                isAnimationActive={false}
              />
            ) : null}
            {shortfallRow ? (
              <ReferenceDot
                x={shortfallRow.on}
                y={shortfallRow.before}
                r={5}
                fill="var(--color-danger)"
                stroke="var(--color-surface)"
                ifOverflow="extendDomain"
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="sr-only">{summary}</p>
      <ul
        data-testid="cashflow-legend"
        className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted"
      >
        <li>
          <span aria-hidden="true" className="text-chart-1">
            ━
          </span>{" "}
          {hasAfter ? t("chat.cf.before") : t("cf.legend.balance")}
        </li>
        {hasAfter ? (
          <li>
            <span aria-hidden="true" className="text-chart-3">
              ┅
            </span>{" "}
            {t("chat.cf.after")}
          </li>
        ) : null}
        <li>
          <span aria-hidden="true" className="text-danger">
            ▒
          </span>{" "}
          {t("chat.cf.belowBuffer", { amount: money(d.min_buffer) })}
        </li>
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
      {d.upcoming.length > 0 ? (
        <div>
          <p className="mb-1 text-xs font-semibold text-muted">
            {t("chat.cf.upcoming")}
          </p>
          <ul className="space-y-1 text-xs text-ink">
            {d.upcoming.map((p, i) => (
              <li key={`${p.on}-${i}`} className="flex items-start gap-2">
                <span className="w-14 shrink-0 text-muted">
                  {formatDay(p.on, lang)}
                </span>
                <span className="min-w-0 flex-1 break-words">{p.label}</span>
                <span className="shrink-0 font-semibold">{money(p.amount)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </CardShell>
  );
}
