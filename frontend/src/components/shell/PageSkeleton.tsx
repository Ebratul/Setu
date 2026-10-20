"use client";

import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";

type Props = { variant?: "list" | "dashboard" | "detail" | "chat" };

/** Route-level loading placeholder: announces itself once and mirrors the page's rough shape. */
export function PageSkeleton({ variant = "list" }: Props) {
  const t = useT();
  return (
    <div role="status" aria-busy="true" data-testid="page-skeleton" className="space-y-4">
      <span className="sr-only">{t("loadingx.page")}</span>
      <Skeleton className="h-8 w-48" />
      {variant === "dashboard" ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-28" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </>
      ) : variant === "detail" ? (
        <>
          <Skeleton className="h-24" />
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-56" />
            <Skeleton className="h-56" />
          </div>
        </>
      ) : variant === "chat" ? (
        <>
          <Skeleton className="h-96" />
          <Skeleton className="h-14" />
        </>
      ) : (
        <>
          <Skeleton className="h-12" />
          <Skeleton className="h-72" />
        </>
      )}
    </div>
  );
}
