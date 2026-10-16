"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { getOrders } from "@/lib/api/analysis";
import { useApi } from "@/lib/useApi";

import { DealMoney } from "./DealMoney";
import { StatusBadge } from "./StatusBadge";

const linkClass =
  "font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none";

export function OrdersTable() {
  const t = useT();
  const { data, error, reload } = useApi(getOrders, "orders");

  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) {
    return (
      <div aria-busy="true" className="space-y-2">
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
      </div>
    );
  }
  if (data.orders.length === 0) {
    return <EmptyState title={t("orders.empty")} />;
  }
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-176 text-sm">
        <caption className="sr-only">{t("orders.caption")}</caption>
        <thead>
          <tr className="border-b border-line text-left text-muted">
            <th scope="col" className="p-3 font-medium">
              {t("orders.ref")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("orders.titleCol")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("orders.supplier")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("orders.status")}
            </th>
            <th scope="col" className="p-3 text-right font-medium">
              {t("orders.goodsValue")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("orders.actions")}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.orders.map((o) => (
            <tr key={o.id} className="border-b border-line last:border-0">
              <th scope="row" className="p-3 text-left font-semibold">
                <Link href={`/app/orders/${o.reference}`} className={linkClass}>
                  {o.reference}
                </Link>
              </th>
              <td className="p-3">{o.title}</td>
              <td className="p-3">
                {o.supplier_name}
                {o.supplier_kyb_status !== "VERIFIED" ? (
                  <span className="ml-2">
                    <Badge tone="warning" icon="⚠">
                      {t(`kyb.${o.supplier_kyb_status}`)}
                    </Badge>
                  </span>
                ) : null}
              </td>
              <td className="p-3">
                <StatusBadge status={o.status} />
              </td>
              <td className="p-3 text-right tabular-nums">
                <DealMoney value={o.goods_value} currency={o.currency} />
              </td>
              <td className="p-3">
                <Link
                  href={`/app/orders/${o.reference}/analysis`}
                  className={linkClass}
                >
                  {t("orders.viewAnalysis")}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
