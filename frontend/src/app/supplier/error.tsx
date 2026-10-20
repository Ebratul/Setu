"use client";

import { ErrorState } from "@/components/ui/ErrorState";

export default function Error({ reset }: { reset: () => void }) {
  return <ErrorState onRetry={reset} />;
}
