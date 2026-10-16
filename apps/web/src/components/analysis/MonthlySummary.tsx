"use client";

import { useState } from "react";

import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { getDemoUsers, getMe } from "@/lib/api/auth";
import { pickLang, useLang, useT } from "@/i18n";
import { getMonthly, type Currency } from "@/lib/api/analysis";
import { formatMoney, formatPct, formatSigned } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { CurrencyToggle } from "./CurrencyToggle";
import { DealLinkRow } from "./DealLinkRow";
import { FxNote } from "./FxNote";
import { HistoryChart } from "./HistoryChart";
import { KpiCard } from "./KpiCard";

export function MonthlySummary() {
  const t = useT();
  const { lang } = useLang();
  const [month, setMonth] = useState<string>("");
  const [party, setParty] = useState<string>("");
  const [currency, setCurrency] = useState<Currency>("USD");

  const me = useApi(getMe, "me-role");
  const needsPicker = me.data?.role === "ADMIN" || me.data?.role === "JUDGE";
  const users = useApi(getDemoUsers, "users-for-picker", needsPicker);
  const { data, error, loading, reload } = useApi(
    (s) => getMonthly(month || undefined, party || undefined, s),
    `${month}|${party}`,
    me.data !== undefined && (!needsPicker || party !== ""),
  );
  const buyers = (users.data?.users ?? []).filter(
    (u) => u.role === "BUYER" && u.party_id,
  );

  const effectiveMonth = month || data?.month || "";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-4">
        <div className="w-44">
          <FormField id="month" label={t("monthly.pickMonth")}>
            {(aria) => (
              <input
                {...aria}
                type="month"
                value={effectiveMonth}
                onChange={(e) => e.target.value && setMonth(e.target.value)}
                className={inputClass}
              />
            )}
          </FormField>
        </div>
        {needsPicker ? (
          <div className="w-64">
            <FormField id="buyer" label={t("monthly.pickBuyer")}>
              {(aria) => (
                <select
                  {...aria}
                  value={party}
                  onChange={(e) => setParty(e.target.value)}
                  className={inputClass}
                >
                  <option value="">{t("monthly.chooseBuyer")}</option>
                  {buyers.map((b) => (
                    <option key={b.party_id} value={b.party_id ?? ""}>
                      {b.party_name}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
          </div>
        ) : null}
        <CurrencyToggle value={currency} onChange={setCurrency} />
      </div>

      {needsPicker && !party ? (
        <EmptyState title={t("monthly.chooseBuyerFirst")} />
      ) : me.error || error ? (
        <QueryError
          error={me.error ?? error}
          onRetry={me.error ? me.reload : reload}
        />
      ) : !data ? (
        <div aria-busy="true" className="space-y-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="space-y-6" aria-busy={loading ? true : undefined}>
          <h2 className="text-lg font-semibold text-ink">
            {data.party_name} · {data.month}
          </h2>
          {data.deals_count === 0 ? (
            <EmptyState
              title={t("monthly.empty")}
              body={t("monthly.emptyHint")}
            />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <KpiCard
                  label={t("monthly.kpi.deals")}
                  value={String(data.deals_count)}
                />
                <KpiCard
                  label={t("monthly.kpi.purchases")}
                  value={formatMoney(
                    data.total_purchases[currency],
                    currency,
                    lang,
                  )}
                  hint={
                    data.change.purchases_pct
                      ? t("monthly.vsPrev", {
                          pct: formatSigned(data.change.purchases_pct, lang),
                        })
                      : undefined
                  }
                />
                <KpiCard
                  label={t("monthly.kpi.landed")}
                  value={formatMoney(
                    data.total_landed_cost[currency],
                    currency,
                    lang,
                  )}
                />
                <KpiCard
                  label={t("monthly.kpi.margin")}
                  value={
                    data.average_margin_pct
                      ? formatPct(data.average_margin_pct, lang)
                      : "—"
                  }
                  hint={
                    data.top_cost_driver
                      ? t("monthly.topDriver", {
                          kind: t(`kind.${data.top_cost_driver.kind}`),
                          share: formatPct(
                            data.top_cost_driver.share_pct,
                            lang,
                          ),
                        })
                      : undefined
                  }
                />
              </div>
              <Card as="section" labelledBy="insights-h">
                <h3 id="insights-h" className="text-lg font-semibold text-ink">
                  {t("monthly.insights")}
                </h3>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink">
                  {data.insights.map((i) => (
                    <li key={i.code}>{pickLang(i, lang)}</li>
                  ))}
                </ul>
              </Card>
              <Card as="section" labelledBy="hist-h">
                <h3 id="hist-h" className="mb-3 text-lg font-semibold text-ink">
                  {t("monthly.history")}
                </h3>
                <HistoryChart history={data.history} currency={currency} />
              </Card>
              <Card
                as="section"
                labelledBy="deals-h"
                className="overflow-x-auto"
              >
                <h3
                  id="deals-h"
                  className="mb-3 text-lg font-semibold text-ink"
                >
                  {t("monthly.deals")}
                </h3>
                <table className="w-full min-w-120 text-sm">
                  <caption className="sr-only">
                    {t("monthly.dealsCaption")}
                  </caption>
                  <thead>
                    <tr className="border-b border-line text-left text-muted">
                      <th scope="col" className="py-2 font-medium">
                        {t("orders.ref")}
                      </th>
                      <th scope="col" className="py-2 font-medium">
                        {t("orders.supplier")}
                      </th>
                      <th scope="col" className="py-2 text-right font-medium">
                        {t("analysis.kpi.landedCost")}
                      </th>
                      <th scope="col" className="py-2 text-right font-medium">
                        {t("analysis.kpi.margin")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.deals.map((d) => (
                      <DealLinkRow
                        key={d.reference}
                        deal={d}
                        currency={currency}
                      />
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
          <FxNote fx={data.fx} />
        </div>
      )}
    </div>
  );
}
