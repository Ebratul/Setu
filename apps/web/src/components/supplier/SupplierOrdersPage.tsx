"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/analysis/StatusBadge";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { listDeals } from "@/lib/api/deals";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { Bi } from "./Bi";

export function SupplierOrdersPage() {
  const t = useT();
  const { lang } = useLang();
  const { data, error, reload } = useApi((s) => listDeals(undefined, s), "sp-deals");
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-ink">
        <Bi k="sp.orders" />
      </h1>
      {error ? (
        <QueryError error={error} onRetry={reload} />
      ) : !data ? (
        <Skeleton className="h-40" />
      ) : data.deals.length === 0 ? (
        <EmptyState title={t("sp.empty")} />
      ) : (
        <ul className="space-y-3">
          {data.deals.map((d) => (
            <li
              key={d.id}
              data-testid="supplier-order"
              className="rounded-card bg-surface p-4 shadow-card"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link
                    href={`/supplier/${encodeURIComponent(d.reference)}`}
                    className="font-bold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                  >
                    {d.reference}
                  </Link>
                  <p className="text-sm text-ink">{d.title}</p>
                  <p className="text-xs text-muted">{t("sp.buyer", { name: d.buyer_name })}</p>
                </div>
                <StatusBadge status={d.status} />
              </div>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-muted">{t("sp.orderValue")}</dt>
                  <dd className="font-semibold tabular-nums">{formatMoney(d.goods_value, d.currency, lang)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("sp.secured")}</dt>
                  <dd className="font-semibold tabular-nums">{formatMoney(d.balance, d.currency, lang)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("sp.nextMilestone")}</dt>
                  <dd className="font-semibold">
                    {d.next_milestone
                      ? `${t(`trigger.${d.next_milestone.trigger}`)} · ${formatDate(d.next_milestone.due_on, lang)}`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
