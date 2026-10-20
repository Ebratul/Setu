"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/analysis/StatusBadge";
import { KybBadge } from "@/components/kyb/KybBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { inputClass } from "@/components/ui/FormField";
import { useLang, useT } from "@/i18n";
import { listDeals, type DealStatus } from "@/lib/api/deals";
import type { KybBadgeStatus } from "@/lib/api/kyb";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const FILTERS: (DealStatus | "ALL")[] = [
  "ALL",
  "DRAFT",
  "PROPOSED",
  "CONFIRMED",
  "FUNDED",
  "IN_PRODUCTION",
  "SHIPPED",
  "ARRIVED",
  "COMPLETED",
  "DISPUTED",
  "CANCELLED",
];
const KYB = ["VERIFIED", "WARNING", "BLOCKED", "PENDING"];

const linkCls =
  "font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function DealsListPage() {
  const t = useT();
  const { lang } = useLang();
  const [status, setStatus] = useState<DealStatus | "ALL">("ALL");
  const [query, setQuery] = useState("");
  const { data, error, reload } = useApi(
    (s) => listDeals(status === "ALL" ? undefined : status, s),
    `deals|${status}`,
  );

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!data) return [];
    if (!q) return data.deals;
    return data.deals.filter((d) =>
      [d.reference, d.title, d.supplier_name].some((x) =>
        x.toLowerCase().includes(q),
      ),
    );
  }, [data, query]);

  const canCreate = data?.viewer_role === "BUYER" || data?.viewer_role === "ADMIN";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("deals.title")}</h1>
          <SimulatedBadge />
        </div>
        {canCreate ? (
          <Link
            href="/app/deals/new"
            className="rounded-xl bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {t("deals.new")}
          </Link>
        ) : null}
      </div>

      <div className="space-y-3">
        <div role="group" aria-label={t("deals.filterLabel")} className="flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={status === f}
              onClick={() => setStatus(f)}
              className={`rounded-full border px-3 py-1 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                status === f
                  ? "border-brand-700 bg-brand-700 text-white"
                  : "border-line bg-surface text-ink hover:bg-brand-50"
              }`}
            >
              {status === f ? "✓ " : ""}
              {f === "ALL" ? t("deals.all") : t(`status.${f}`)}
            </button>
          ))}
        </div>
        <div className="max-w-sm">
          <label htmlFor="deal-search" className="mb-1 block text-sm font-medium text-ink">
            {t("deals.search")}
          </label>
          <input
            id="deal-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("deals.searchPlaceholder")}
            className={inputClass}
          />
        </div>
      </div>

      {error ? (
        <QueryError error={error} onRetry={reload} />
      ) : !data ? (
        <Skeleton className="h-48" />
      ) : shown.length === 0 ? (
        data.deals.length === 0 && status === "ALL" ? (
          <EmptyState
            icon="box"
            title={t("emptyx.dealsTitle")}
            body={t("emptyx.dealsBody")}
            action={
              canCreate ? (
                <Link
                  href="/app/deals/new"
                  className="inline-flex min-h-11 items-center rounded-xl bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  {t("emptyx.dealsCta")}
                </Link>
              ) : undefined
            }
          />
        ) : (
          <EmptyState
            icon="search"
            title={t("deals.empty")}
            body={t("emptyx.dealsFilteredBody")}
          />
        )
      ) : (
        <div className="overflow-x-auto rounded-card bg-surface p-3 shadow-card">
          <p aria-live="polite" className="sr-only">
            {t("deals.count", { n: shown.length })}
          </p>
          <table className="w-full min-w-208 text-sm" data-testid="deals-table">
            <caption className="sr-only">{t("deals.caption")}</caption>
            <thead>
              <tr className="border-b border-line text-left text-muted">
                <th scope="col" className="py-2 pr-3 font-medium">{t("orders.ref")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("orders.supplier")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("deals.goods")}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t("orders.goodsValue")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("dash.nextMilestone")}</th>
                <th scope="col" className="py-2 font-medium">{t("orders.status")}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((d) => {
                const kyb = (KYB.includes(d.supplier_kyb_status)
                  ? d.supplier_kyb_status
                  : "PENDING") as KybBadgeStatus;
                const nm = d.next_milestone;
                return (
                  <tr key={d.id} data-testid="deal-row" className="border-b border-line align-top last:border-0">
                    <th scope="row" className="py-3 pr-3 text-left">
                      <Link href={`/app/deals/${encodeURIComponent(d.reference)}`} className={linkCls}>
                        {d.reference}
                      </Link>
                    </th>
                    <td className="py-3 pr-3">
                      <span className="block">{d.supplier_name}</span>
                      <KybBadge status={kyb} />
                    </td>
                    <td className="py-3 pr-3">{d.title}</td>
                    <td className="py-3 pr-3 text-right tabular-nums">
                      {formatMoney(d.goods_value, d.currency, lang)}
                    </td>
                    <td className="py-3 pr-3">
                      {nm ? (
                        <>
                          <span className="block">
                            {t("dash.milestone", { seq: nm.seq })} · {t(`trigger.${nm.trigger}`)}
                          </span>
                          <span className="block text-xs text-muted tabular-nums">
                            {formatMoney(nm.amount, nm.currency, lang)} · {formatDate(nm.due_on, lang)}
                          </span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3">
                      <StatusBadge status={d.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
