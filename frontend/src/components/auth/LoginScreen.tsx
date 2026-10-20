"use client";

import { Suspense } from "react";

import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { Skeleton } from "@/components/ui/Skeleton";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { LoginPanel } from "./LoginPanel";

export function LoginScreen() {
  const t = useT();
  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <span className="text-lg font-bold text-brand-text">Setu সেতু</span>
          <div className="flex items-center gap-3">
            <SimulatedBadge />
            <LanguageToggle />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
        <h1 className="text-2xl font-bold text-ink">{t("login.title")}</h1>
        <p
          role="note"
          className="mt-3 rounded-xl border border-warning bg-warning-soft p-3 text-sm text-ink"
        >
          {t("login.demoOnly")}
        </p>
        <div className="mt-6">
          <Suspense fallback={<Skeleton className="h-40" />}>
            <LoginPanel />
          </Suspense>
        </div>
      </main>
    </>
  );
}
