"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { BackButton } from "@/components/ui/BackButton";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useT } from "@/i18n";

export function PublicHeader() {
  const t = useT();
  const pathname = usePathname();
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
      >
        {t("landing.skip")}
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2 sm:px-6">
          <nav aria-label={t("landing.nav.label")} className="flex items-center gap-3">
            {pathname !== "/" ? <BackButton fallbackHref="/" /> : null}
            <Link
              href="/"
              className="inline-flex min-h-11 items-center text-lg font-bold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              Setu সেতু
            </Link>
            <Link
              href="/judges"
              className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("judges.nav")}
            </Link>
            <Link
              href="/docs"
              className="inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("docs.link")}
            </Link>
          </nav>
          <div className="flex flex-wrap items-center gap-3">
            <LanguageToggle withZh />
            <ThemeToggle />
          </div>
        </div>
      </header>
    </>
  );
}
