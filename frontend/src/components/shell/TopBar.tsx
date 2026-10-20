"use client";

import Link from "next/link";

import { HelpButton } from "@/components/docs/HelpButton";
import { Icon } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useT } from "@/i18n";

import { DigitsToggle } from "./DigitsToggle";
import { LanguageToggle } from "./LanguageToggle";
import { MobileNav } from "./MobileNav";
import { NotificationBell } from "./NotificationBell";
import { UserMenu } from "./UserMenu";

type Props = {
  variant?: "app" | "supplier";
  showBell?: boolean;
  onSearch?: () => void;
};

/** Sticky header shared by the buyer/admin shell and the supplier portal. */
export function TopBar({ variant = "app", showBell = false, onSearch }: Props) {
  const t = useT();
  const supplier = variant === "supplier";
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface shadow-card">
      <div
        className={`mx-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2 ${
          supplier ? "max-w-5xl" : "max-w-7xl"
        }`}
      >
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {supplier ? null : <MobileNav />}
          <Link
            href={supplier ? "/supplier" : "/"}
            className="inline-flex min-h-11 items-center rounded-md text-lg font-bold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            {supplier ? "Setu 供应商" : "Setu সেতু"}
          </Link>
          <SimulatedBadge />
        </div>
        <div role="group" aria-label={t("topbar.controls")} className="flex flex-wrap items-center gap-2 sm:gap-3">
          {onSearch ? (
            <button
              type="button"
              data-testid="open-palette"
              aria-haspopup="dialog"
              aria-label={t("topbar.searchHint")}
              onClick={onSearch}
              className="flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-sm text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <Icon name="search" />
              <span className="hidden sm:inline">{t("topbar.search")}</span>
              <kbd className="hidden rounded border border-line px-1.5 text-xs lg:inline">Ctrl K</kbd>
            </button>
          ) : null}
          {supplier ? (
            <Link
              href="/supplier/team"
              className="inline-flex min-h-11 items-center rounded-md px-2 text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("nav.team")}
            </Link>
          ) : null}
          <HelpButton />
          <LanguageToggle withZh={supplier} />
          <DigitsToggle />
          <ThemeToggle />
          {showBell ? <NotificationBell supplier={supplier} /> : null}
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
