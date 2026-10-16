"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";

import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";

type Props = { error: unknown; onRetry?: () => void };

/** Maps an API failure to redirect-to-login (401), no-access (403), not-found (404) or retryable error. */
export function QueryError({ error, onRetry }: Props) {
  const t = useT();
  const router = useRouter();
  const status = error instanceof ApiError ? error.status : 0;

  useEffect(() => {
    if (status === 401) {
      router.replace(
        `/login?next=${encodeURIComponent(window.location.pathname)}`,
      );
    }
  }, [status, router]);

  if (status === 401) {
    return <p role="status">{t("common.redirectingLogin")}</p>;
  }
  if (status === 403) {
    return (
      <EmptyState
        title={t("error.noAccessTitle")}
        body={t("error.noAccessBody")}
        action={
          <Link
            href="/app/orders"
            className="font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500"
          >
            {t("nav.orders")}
          </Link>
        }
      />
    );
  }
  if (status === 404) {
    return <EmptyState title={t("error.notFoundTitle")} />;
  }
  return (
    <ErrorState
      onRetry={onRetry}
      message={
        error instanceof ApiError && error.detail ? error.detail : undefined
      }
    />
  );
}
