"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { PublicFooter } from "@/components/landing/PublicFooter";
import { Alert } from "@/components/ui/Alert";
import { BackButton } from "@/components/ui/BackButton";
import { Button } from "@/components/ui/Button";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { Skeleton } from "@/components/ui/Skeleton";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";
import { useAuthMode } from "@/lib/auth/useAuthMode";

type Props = {
  title: string;
  lead?: string;
  /** Pages that only make sense with real sign-in show an info screen in demo mode. */
  neonOnly?: boolean;
  children: ReactNode;
};

const linkClass =
  "inline-flex min-h-11 items-center rounded-md px-1 font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
export { linkClass as authLinkClass };

export function AuthShell({ title, lead, neonOnly = false, children }: Props) {
  const t = useT();
  const { mode, failed, retry } = useAuthMode();
  let body: ReactNode;
  if (failed) {
    body = (
      <Alert
        tone="danger"
        urgent
        action={
          <Button size="sm" onClick={retry}>
            {t("common.retry")}
          </Button>
        }
      >
        {t("auth.configError")}
      </Alert>
    );
  } else if (mode === null) {
    body = <Skeleton className="h-40" />;
  } else if (neonOnly && mode === "demo") {
    body = (
      <div className="space-y-3">
        <Alert tone="info">{t("auth.unavailable.body")}</Alert>
        <Link href="/login" className={linkClass}>
          {t("auth.unavailable.toLogin")}
        </Link>
      </div>
    );
  } else {
    body = children;
  }
  return (
    <>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <span className="text-lg font-bold text-brand-text">Setu সেতু</span>
          <div className="flex items-center gap-3">
            <SimulatedBadge />
            <LanguageToggle withZh />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
        <BackButton href="/" className="mb-4 -ml-2" />
        <h1 className="text-2xl font-bold text-ink">{title}</h1>
        {lead && mode === "neon" ? (
          <p className="mt-2 text-sm text-muted">{lead}</p>
        ) : null}
        <div className="mt-6" aria-busy={mode === null && !failed}>
          {body}
        </div>
      </main>
      <PublicFooter />
    </>
  );
}
