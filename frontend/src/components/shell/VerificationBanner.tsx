"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/Alert";
import { useT } from "@/i18n";
import type { AppUser } from "@/lib/api/auth";
import { useShellUser } from "@/lib/MeContext";

const LOCKED = ["orders", "escrow", "fx", "team"] as const;

/** Shown across /app and /supplier until the account is ACTIVE: what is locked, why, and the next step. */
export function VerificationBanner({ user }: { user?: AppUser }) {
  const t = useT();
  const ctx = useShellUser();
  const me = user ?? ctx;
  const status = me?.account_status;
  if (!me || !status || status === "ACTIVE") return null;
  const admin = me.role === "ADMIN";
  const key = admin
    ? "admin"
    : status === "PENDING_PROFILE"
      ? "profile"
      : status === "PENDING_VERIFICATION"
        ? "review"
        : "blocked";
  const href = admin
    ? "/onboarding?step=security"
    : status === "PENDING_PROFILE"
      ? "/onboarding"
      : "/onboarding/status";
  return (
    <div className="mb-4" data-testid="verification-banner">
      <Alert
        tone="warning"
        title={t(`vb.${key}.title`)}
        action={
          <Link
            href={href}
            className="inline-flex min-h-11 items-center rounded-md px-2 font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            {t(`vb.${key}.cta`)}
          </Link>
        }
      >
        <p>{t(`vb.${key}.body`)}</p>
        {!admin ? (
          <>
            <p className="mt-2 font-semibold">{t("vb.locked.title")}</p>
            <ul className="list-disc pl-5">
              {LOCKED.map((k) => (
                <li key={k}>{t(`vb.locked.${k}`)}</li>
              ))}
            </ul>
            <p className="mt-2 text-muted">{t("vb.open")}</p>
          </>
        ) : null}
      </Alert>
    </div>
  );
}
