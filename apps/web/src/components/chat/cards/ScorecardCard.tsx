"use client";

import { Badge } from "@/components/ui/Badge";
import { hasKey, useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatDecimal, formatPct } from "@/lib/format";

import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "scorecard" }>;

export function ScorecardCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const pct = (v: string | null) => (v ? formatPct(v, lang) : "—");
  return (
    <CardShell
      type="scorecard"
      title={t("chat.card.scorecard")}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref="/app/analysis"
      linkLabel={t("chat.card.openAnalysis")}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <caption className="sr-only">{t("suppliers.caption")}</caption>
          <thead>
            <tr className="border-b border-line text-muted">
              <th scope="col" className="py-1 pr-2 font-semibold">
                {t("suppliers.col.name")}
              </th>
              <th scope="col" className="px-1 py-1 font-semibold">
                {t("suppliers.col.score")}
              </th>
              <th scope="col" className="px-1 py-1 font-semibold">
                {t("suppliers.col.onTime")}
              </th>
              <th scope="col" className="px-1 py-1 font-semibold">
                {t("suppliers.col.dispute")}
              </th>
            </tr>
          </thead>
          <tbody>
            {card.data.suppliers.map((s) => (
              <tr
                key={s.code}
                data-weak={s.weak}
                className={`border-b border-line align-top ${s.weak ? "bg-danger-soft" : ""}`}
              >
                <th scope="row" className="py-1.5 pr-2 font-semibold text-ink">
                  <span className="break-words">{s.name}</span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    {s.weak ? (
                      <Badge tone="danger" icon="⚠">
                        {t("suppliers.weak")}
                      </Badge>
                    ) : null}
                    {s.kyb_status !== "VERIFIED" && hasKey(`kyb.${s.kyb_status}`) ? (
                      <Badge tone="warning" icon="▲">
                        {t(`kyb.${s.kyb_status}`)}
                      </Badge>
                    ) : null}
                  </span>
                </th>
                <td className="px-1 py-1.5 font-bold text-ink">
                  {s.score ? formatDecimal(s.score, lang, 2) : "—"}
                </td>
                <td className="px-1 py-1.5 text-ink">{pct(s.on_time_rate_pct)}</td>
                <td className="px-1 py-1.5 text-ink">{pct(s.dispute_rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardShell>
  );
}
