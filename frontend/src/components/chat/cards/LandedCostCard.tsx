"use client";

import { hasKey, useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatMoney, formatPct, type Currency } from "@/lib/format";

import { CardShell, Kpi } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "landed_cost" }>;

const SWATCH = [
  "bg-chart-1",
  "bg-chart-2",
  "bg-chart-3",
  "bg-chart-4",
  "bg-chart-5",
  "bg-chart-6",
];

export function LandedCostCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const cur = d.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);
  const lineName = (kind: string, label: string | null) => {
    const k = `kind.${kind}`;
    return hasKey(k) ? t(k) : (label ?? kind);
  };
  const bandKey = d.margin_band ? `band.${d.margin_band}` : null;
  return (
    <CardShell
      type="landed_cost"
      title={t("chat.card.landed_cost", { deal: d.deal_ref ?? "" })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref={d.analysis_route}
      linkLabel={t("chat.card.openAnalysis")}
    >
      <dl className="grid grid-cols-2 gap-2">
        <Kpi label={t("analysis.kpi.landedCost")} value={money(d.landed_cost)} />
        <Kpi
          label={t("chat.landed.perUnit", { unit: d.unit })}
          value={money(d.cost_per_unit)}
        />
        <Kpi
          label={t("chat.landed.marginPct")}
          value={
            d.gross_margin_pct ? (
              <>
                {formatPct(d.gross_margin_pct, lang)}
                {bandKey && hasKey(bandKey) ? (
                  <span className="ml-1 text-xs font-semibold text-muted">
                    ({t(bandKey)})
                  </span>
                ) : null}
              </>
            ) : (
              t("analysis.kpi.noPrice")
            )
          }
        />
        <Kpi
          label={t("chat.landed.breakEven", { unit: d.unit })}
          value={money(d.break_even_price_per_unit)}
        />
      </dl>
      <div>
        <p className="mb-1 text-xs font-semibold text-muted">
          {t("analysis.breakdown.title")}
        </p>
        <div
          aria-hidden="true"
          className="flex h-3 w-full overflow-hidden rounded-full bg-surface-alt"
        >
          {d.lines.map((l, i) => (
            <div
              key={`${l.kind}-${i}`}
              className={SWATCH[i % SWATCH.length]}
              style={{ width: `${Number(l.share_pct)}%` }}
            />
          ))}
        </div>
        <ul className="mt-2 space-y-1 text-xs text-ink">
          {d.lines.map((l, i) => (
            <li key={`${l.kind}-${i}`} className="flex items-start gap-2">
              <span
                aria-hidden="true"
                className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-sm ${SWATCH[i % SWATCH.length]}`}
              />
              <span className="min-w-0 flex-1 break-words">
                {lineName(l.kind, l.label)}
              </span>
              <span className="shrink-0 font-semibold">
                {money(l.amount)} · {formatPct(l.share_pct, lang)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </CardShell>
  );
}
