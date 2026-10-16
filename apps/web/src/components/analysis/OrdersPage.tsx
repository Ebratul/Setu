"use client";

import { useT } from "@/i18n";

import { OrdersTable } from "./OrdersTable";

export function OrdersPage() {
  const t = useT();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-ink">{t("orders.title")}</h1>
      <OrdersTable />
    </div>
  );
}
