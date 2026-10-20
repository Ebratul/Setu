"use client";

import Link from "next/link";

import { useT } from "@/i18n";

const link =
  "inline-flex min-h-11 items-center rounded-lg font-semibold text-brand-text underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function PublicFooter() {
  const t = useT();
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid w-full max-w-6xl gap-4 px-4 py-8 text-sm text-muted sm:px-6">
        <p className="font-semibold text-ink">{t("landing.footer.team")}</p>
        <p>{t("landing.footer.simulated")}</p>
        <p>{t("landing.footer.licences")}</p>
        <nav aria-label={t("landing.footer.nav")} className="flex flex-wrap gap-x-6">
          <Link href="/accessibility" className={link}>
            {t("landing.footer.a11y")}
          </Link>
          <a href="/CREDITS.md" className={link}>
            {t("landing.footer.credits")}
          </a>
          <Link href="/verify" className={link}>
            {t("landing.footer.verify")}
          </Link>
          <a href="https://github.com/" rel="noopener noreferrer" className={link}>
            {t("landing.footer.github")}
          </a>
        </nav>
      </div>
    </footer>
  );
}
