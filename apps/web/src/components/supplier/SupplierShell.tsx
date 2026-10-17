"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { UserMenu } from "@/components/shell/UserMenu";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ToastProvider } from "@/components/ui/Toast";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { useApi } from "@/lib/useApi";

/** Supplier portal frame. Only SUPPLIER users see it; everyone else is sent to /app. */
export function SupplierShell({ children }: { children: ReactNode }) {
  const t = useT();
  const router = useRouter();
  const me = useApi((s) => getMe(s), "me");
  const wrongRole = me.data !== undefined && me.data.role !== "SUPPLIER";

  useEffect(() => {
    if (wrongRole) router.replace("/app");
  }, [wrongRole, router]);

  return (
    <ToastProvider>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-700 focus:ring-2 focus:ring-brand-500"
      >
        {t("shell.skip")}
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-3">
            <Link
              href="/supplier"
              className="text-lg font-bold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              Setu 供应商
            </Link>
            <SimulatedBadge />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <LanguageToggle withZh />
            <UserMenu />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-5xl min-w-0 flex-1 px-4 py-6">
        {me.error ? (
          <QueryError error={me.error} onRetry={me.reload} />
        ) : me.loading || wrongRole ? (
          <Skeleton className="h-64" />
        ) : (
          children
        )}
      </main>
      <footer className="px-4 py-6 text-center text-sm text-muted">
        {t("common.footer")}
      </footer>
    </ToastProvider>
  );
}
