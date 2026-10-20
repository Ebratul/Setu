export const instant = false;

import { Suspense } from "react";

import { CashflowPage } from "@/components/cashflow/CashflowPage";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <CashflowPage />
    </Suspense>
  );
}
