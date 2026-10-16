import { Suspense } from "react";

import { FinancingPlaceholder } from "@/components/cashflow/FinancingPlaceholder";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-40" />}>
      <FinancingPlaceholder />
    </Suspense>
  );
}
