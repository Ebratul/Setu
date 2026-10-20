"use client";

import Link from "next/link";
import { useState } from "react";

import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useT } from "@/i18n";

import { ButtonLink } from "./ButtonLink";

const NAV = [
  { id: "how", href: "#how" },
  { id: "features", href: "#features" },
  { id: "security", href: "#security" },
  { id: "demo", href: "#demo" },
] as const;

const linkClass =
  "inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

export function LandingHeader() {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
      >
        {t("landing.skip")}
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2 sm:px-6">
          <Link
            href="/"
            className="inline-flex min-h-11 items-center text-lg font-bold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            Setu সেতু
          </Link>
          <nav aria-label={t("landing.nav.label")} className="hidden items-center gap-1 lg:flex">
            {NAV.map((n) => (
              <a key={n.id} href={n.href} className={linkClass}>
                {t(`landing.nav.${n.id}`)}
              </a>
            ))}
          </nav>
          <div className="hidden items-center gap-3 lg:flex">
            <LanguageToggle withZh />
            <ThemeToggle />
            <ButtonLink href="/demo" variant="accent">
              {t("landing.cta.run")}
            </ButtonLink>
          </div>
          <button
            type="button"
            aria-label={t("landing.nav.menu")}
            aria-haspopup="dialog"
            aria-expanded={open}
            onClick={() => setOpen(true)}
            className="flex size-11 items-center justify-center rounded-xl border border-line text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none lg:hidden"
          >
            <Icon name="menu" />
          </button>
        </div>
      </header>
      {open ? (
        <Drawer title={t("landing.nav.menuTitle")} onClose={() => setOpen(false)}>
          <nav aria-label={t("landing.nav.label")} className="grid gap-1">
            {NAV.map((n) => (
              <a key={n.id} href={n.href} className={linkClass} onClick={() => setOpen(false)}>
                {t(`landing.nav.${n.id}`)}
              </a>
            ))}
          </nav>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <LanguageToggle withZh />
            <ThemeToggle />
          </div>
          <ButtonLink href="/demo" variant="accent" className="mt-6 w-full">
            {t("landing.cta.run")}
          </ButtonLink>
        </Drawer>
      ) : null}
    </>
  );
}
