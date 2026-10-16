"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { getForecast } from "@/lib/api/cashflow";
import { useApi } from "@/lib/useApi";

import { CashflowChart } from "./CashflowChart";

type Props = { partyId?: string };

export function MiniCashflow({ partyId }: Props) {
  const t = useT();
  const { data, error, reload } = useApi(
    (s) => getForecast(partyId, 90, undefined, s),
    `mini-forecast|${partyId ?? ""}`,
  );
  return (
    <Card as="section" labelledBy="mini-h" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="mini-h" className="text-lg font-semibold text-ink">
          {t("dash.cashflow")}
        </h2>
        <Link
          href="/app/cashflow"
          className="font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          {t("dash.cashflowLink")}
        </Link>
      </div>
      {error ? (
        <QueryError error={error} onRetry={reload} />
      ) : !data ? (
        <Skeleton className="h-52" />
      ) : (
        <>
          {data.first_shortfall ? null : (
            <p className="text-sm font-semibold text-success">
              ✓ {t("cf.noShortfall", { days: 90 })}
            </p>
          )}
          <CashflowChart forecast={data} compact />
        </>
      )}
    </Card>
  );
}
