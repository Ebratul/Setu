"use client";

import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { AppNav } from "./AppNav";
import { LanguageToggle } from "./LanguageToggle";
import { UserMenu } from "./UserMenu";

export function AppShell({ children }: { children: ReactNode }) {
  const t = useT();
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-700 focus:ring-2 focus:ring-brand-500"
      >
        {t("shell.skip")}
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="text-lg font-bold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              Setu সেতু
            </Link>
            <SimulatedBadge />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <LanguageToggle />
            <UserMenu />
          </div>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-6 md:flex-row md:gap-8">
        <aside className="md:w-48 md:shrink-0">
          <Suspense fallback={null}>
            <AppNav />
          </Suspense>
        </aside>
        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>
      <footer className="px-4 py-6 text-center text-sm text-muted">
        {t("common.footer")}
      </footer>
    </>
  );
}
