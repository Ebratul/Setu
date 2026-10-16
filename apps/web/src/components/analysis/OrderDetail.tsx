"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getOrderAnalysis } from "@/lib/api/analysis";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { DealMoney } from "./DealMoney";
import { StatusBadge } from "./StatusBadge";

export function OrderDetail({ reference }: { reference: string }) {
  const t = useT();
  const { lang } = useLang();
  const { data, error, reload } = useApi(
    (s) => getOrderAnalysis(reference, undefined, s),
    `deal|${reference}`,
  );
  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) return <Skeleton className="h-64" />;
  const deal = data.deal;
  if (!deal) return <QueryError error={null} onRetry={reload} />;
  const rows: [string, React.ReactNode][] = [
    [t("orders.supplier"), deal.supplier_name],
    [t("orders.status"), <StatusBadge key="s" status={deal.status} />],
    [t("orders.hs"), deal.hs_code],
    [t("orders.incoterm"), deal.incoterm],
    [t("orders.quantity"), `${deal.quantity} ${deal.unit}`],
    [
      t("orders.goodsValue"),
      <DealMoney key="g" value={deal.goods_value} currency={deal.currency} />,
    ],
    [t("orders.opened"), formatDate(deal.opened_on, lang)],
  ];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-ink">{deal.reference}</h1>
        <p className="text-muted">{deal.title}</p>
      </div>
      <Card>
        <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Link
        href={`/app/orders/${deal.reference}/analysis`}
        className="inline-block rounded-xl bg-brand-700 px-5 py-3 font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        {t("orders.viewAnalysis")} →
      </Link>
    </div>
  );
}
