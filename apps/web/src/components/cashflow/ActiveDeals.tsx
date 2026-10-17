"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/analysis/StatusBadge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { hasKey, useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import type { DashboardDeal } from "@/lib/api/cashflow";
import { formatDate, formatMoney } from "@/lib/format";

type Props = { deals: DashboardDeal[]; currency: Currency };

export function ActiveDeals({ deals, currency }: Props) {
  const t = useT();
  const { lang } = useLang();
  return (
    <Card as="section" labelledBy="deals-h" className="space-y-3">
      <h2 id="deals-h" className="text-lg font-semibold text-ink">
        {t("dash.deals")}
      </h2>
      {deals.length === 0 ? (
        <EmptyState title={t("dash.noDeals")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-176 text-sm">
            <caption className="sr-only">{t("dash.dealsCaption")}</caption>
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th scope="col" className="py-2 font-medium">
                  {t("orders.ref")}
                </th>
                <th scope="col" className="py-2 font-medium">
                  {t("orders.supplier")}
                </th>
                <th scope="col" className="py-2 font-medium">
                  {t("orders.status")}
                </th>
                <th scope="col" className="py-2 text-right font-medium">
                  {t("orders.goodsValue")}
                </th>
                <th scope="col" className="py-2 font-medium">
                  {t("dash.nextMilestone")}
                </th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => (
                <tr
                  key={d.reference}
                  className="border-b border-line last:border-0"
                >
                  <th scope="row" className="py-2 pr-3 text-left">
                    <Link
                      href={`/app/deals/${encodeURIComponent(d.reference)}`}
                      className="font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                    >
                      {d.reference}
                    </Link>
                    <span className="block text-xs font-normal text-muted">
                      {d.title}
                    </span>
                  </th>
                  <td className="py-2 pr-3">{d.supplier_name}</td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {formatMoney(d.goods_value[currency], currency, lang)}
                  </td>
                  <td className="py-2">
                    {d.next_milestone ? (
                      <span>
                        {t("dash.milestone", { seq: d.next_milestone.seq })}
                        {" · "}
                        {hasKey(`trigger.${d.next_milestone.trigger}`)
                          ? t(`trigger.${d.next_milestone.trigger}`)
                          : d.next_milestone.trigger}
                        <span className="block text-xs text-muted tabular-nums">
                          {formatMoney(
                            d.next_milestone.amount[currency],
                            currency,
                            lang,
                          )}
                          {" · "}
                          {formatDate(d.next_milestone.due_on, lang)}
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
