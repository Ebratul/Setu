"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/ui/ErrorState";

type Props = { error?: Error & { digest?: string }; reset: () => void };

/** Shared body for every error.tsx: friendly message with retry; the raw error is never shown. */
export function RouteError({ error, reset }: Props) {
  useEffect(() => {
    if (error) console.error(error);
  }, [error]);
  return (
    <div data-testid="route-error">
      <ErrorState onRetry={reset} />
    </div>
  );
}
