"use client";

import Link from "next/link";

import { useT } from "@/i18n";

import { OrderAnalysisView } from "./OrderAnalysisView";

export function OrderAnalysisPage({ reference }: { reference: string }) {
  const t = useT();
  return (
    <div className="space-y-4">
      <Link
        href={`/app/orders/${reference}`}
        className="text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        ← {reference}
      </Link>
      <h1 className="text-2xl font-bold text-ink">
        {t("analysis.order.title")} · {reference}
      </h1>
      <OrderAnalysisView reference={reference} />
    </div>
  );
}
