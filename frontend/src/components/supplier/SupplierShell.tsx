"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { DocHint } from "@/components/docs/DocHint";
import { TopBar } from "@/components/shell/TopBar";
import { QueryError } from "@/components/ui/QueryError";
import { BackButton } from "@/components/ui/BackButton";
import { Skeleton } from "@/components/ui/Skeleton";
import { ToastProvider } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";
import { useDigits } from "@/lib/useDigits";
import { useEmbed } from "@/lib/useEmbed";

/** Supplier portal frame. Only SUPPLIER users see it; everyone else is sent to /app. */
export function SupplierShell({ children }: { children: ReactNode }) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const me = useApi((s) => getMe(s), "me");
  const [digits] = useDigits();
  const embed = useEmbed();
  const wrongRole = me.data !== undefined && me.data.role !== "SUPPLIER";

  useEffect(() => {
    if (wrongRole) router.replace("/app");
  }, [wrongRole, router]);

  if (embed) {
    return (
      <ToastProvider>
        <main id="main" className="min-w-0 flex-1 p-3">
          {me.error ? (
            <QueryError error={me.error} onRetry={me.reload} />
          ) : me.loading || wrongRole ? (
            <Skeleton className="h-64" />
          ) : (
            <div key={digits}>{children}</div>
          )}
        </main>
      </ToastProvider>
    );
  }

  return (
    <ToastProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
      >
        {t("shell.skip")}
      </a>
      <TopBar variant="supplier" showBell={me.data?.role === "SUPPLIER"} />
      <main id="main" className="mx-auto w-full max-w-5xl min-w-0 flex-1 px-4 py-6">
        {pathname !== "/supplier" ? (
          <BackButton fallbackHref="/supplier" className="-ml-2 mb-2" />
        ) : null}
        <DocHint userId={me.data?.id} />
        {me.error ? (
          <QueryError error={me.error} onRetry={me.reload} />
        ) : me.loading || wrongRole ? (
          <Skeleton className="h-64" />
        ) : (
          <div key={digits}>{children}</div>
        )}
      </main>
      <footer className="px-4 py-6 text-center text-sm text-muted">
        {t("common.footer")}{" "}
        <Link href="/docs" className="font-semibold text-brand-text underline">
          {t("docs.title")}
        </Link>
      </footer>
    </ToastProvider>
  );
}
