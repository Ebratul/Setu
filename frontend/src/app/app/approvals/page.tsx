export const instant = false;

import { Suspense } from "react";

import { ApprovalsPage } from "@/components/approvals/ApprovalsPage";
import { Skeleton } from "@/components/ui/Skeleton";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <ApprovalsPage />
    </Suspense>
  );
}
