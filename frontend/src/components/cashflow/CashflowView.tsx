"use client";

import { useSearchParams } from "next/navigation";

import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { getForecast } from "@/lib/api/cashflow";
import { useApi } from "@/lib/useApi";

import { CashflowLoaded } from "./CashflowLoaded";

type Props = { partyId?: string };

export function CashflowView({ partyId }: Props) {
  const date = useSearchParams().get("date");
  const { data, error, reload } = useApi(
    (s) => getForecast(partyId, 90, undefined, s),
    `forecast|${partyId ?? ""}`,
  );
  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) {
    return (
      <div aria-busy="true" className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-80" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  return (
    <CashflowLoaded forecast={data} partyId={partyId} initialDate={date} />
  );
}
