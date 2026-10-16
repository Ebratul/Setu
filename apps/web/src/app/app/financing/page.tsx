import { Suspense } from "react";

import { FinancingPage } from "@/components/financing/FinancingPage";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-40" />}>
      <FinancingPage />
    </Suspense>
  );
}
