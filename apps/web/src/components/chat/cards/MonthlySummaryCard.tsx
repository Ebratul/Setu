"use client";

import { hasKey, pickLang, useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatMoney, formatMonth, formatPct, type Currency } from "@/lib/format";

import { CardShell, Kpi } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "monthly_summary" }>;

export function MonthlySummaryCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const cur = d.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);
  const max = Math.max(...d.history.map((h) => Number(h.total_landed_cost)), 0);
  const driverKey = d.top_cost_driver ? `kind.${d.top_cost_driver.kind}` : null;
  return (
    <CardShell
      type="monthly_summary"
      title={t("chat.card.monthly", { month: formatMonth(d.month, lang) })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref="/app/analysis"
      linkLabel={t("chat.card.openAnalysis")}
    >
      <dl className="grid grid-cols-2 gap-2">
        <Kpi label={t("monthly.kpi.deals")} value={d.deals_count} />
        <Kpi label={t("monthly.kpi.purchases")} value={money(d.total_purchases)} />
        <Kpi label={t("monthly.kpi.landed")} value={money(d.total_landed_cost)} />
        <Kpi
          label={t("monthly.kpi.margin")}
          value={d.average_margin_pct ? formatPct(d.average_margin_pct, lang) : "—"}
        />
      </dl>
      {d.top_cost_driver && driverKey && hasKey(driverKey) ? (
        <p className="text-xs text-ink">
          {t("monthly.topDriver", {
            kind: t(driverKey),
            share: formatPct(d.top_cost_driver.share_pct, lang),
          })}
        </p>
      ) : null}
      <div>
        <p className="mb-1 text-xs font-semibold text-muted">
          {t("chat.monthly.history")}
        </p>
        <ul className="flex h-24 items-end gap-1.5">
          {d.history.map((h) => {
            const pct = max > 0 ? (Number(h.total_landed_cost) / max) * 100 : 0;
            return (
              <li
                key={h.month}
                title={`${formatMonth(h.month, lang)}: ${money(h.total_landed_cost)}`}
                className="flex h-full min-w-0 flex-1 flex-col justify-end text-center"
              >
                <div
                  aria-hidden="true"
                  className="w-full rounded-t bg-chart-1"
                  style={{ height: `${Math.max(pct, 2)}%` }}
                />
                <span className="mt-1 block truncate text-[10px] text-muted">
                  {formatMonth(h.month, lang)}
                </span>
                <span className="sr-only">{money(h.total_landed_cost)}</span>
              </li>
            );
          })}
        </ul>
      </div>
      {d.insights.length > 0 ? (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink">
          {d.insights.map((i) => (
            <li key={i.code}>{pickLang(i, lang)}</li>
          ))}
        </ul>
      ) : null}
    </CardShell>
  );
}
