"use client";

import { useState } from "react";

import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { getOrderAnalysis, type Currency } from "@/lib/api/analysis";
import { useApi } from "@/lib/useApi";

import { AnalysisResults } from "./AnalysisResults";
import { useTargetMargin } from "./useTargetMargin";

type Props = { reference: string };

export function AnalysisSkeleton() {
  return (
    <div aria-busy="true" className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

export function OrderAnalysisView({ reference }: Props) {
  const [currency, setCurrency] = useState<Currency>("USD");
  const target = useTargetMargin();
  const { data, error, loading, reload } = useApi(
    (s) => getOrderAnalysis(reference, target.request, s),
    `${reference}|${target.request ?? ""}`,
  );

  if (error) return <QueryError error={error} onRetry={reload} />;
  if (!data) return <AnalysisSkeleton />;
  return (
    <AnalysisResults
      data={data}
      currency={currency}
      onCurrency={setCurrency}
      busy={loading}
      target={{
        value: target.value,
        error: target.error,
        updating: target.updating || loading,
        onChange: target.setValue,
      }}
    />
  );
}
