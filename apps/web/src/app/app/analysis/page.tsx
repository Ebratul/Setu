export const instant = false;

import { Suspense } from "react";

import { AnalysisTabs } from "@/components/analysis/AnalysisTabs";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <AnalysisTabs />
    </Suspense>
  );
}
