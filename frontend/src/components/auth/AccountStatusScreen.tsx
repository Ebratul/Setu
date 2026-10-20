"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { getOnboardingState } from "@/lib/api/onboarding";
import { useApi } from "@/lib/useApi";
import { useAuthMode } from "@/lib/auth/useAuthMode";
import { signOutEverywhere, type StatusReason } from "@/lib/auth/flow";

import { AuthShell, authLinkClass } from "./AuthShell";

const REASONS: Record<string, { key: "notOnboarded" | "pending" | "suspended" | "rejected"; tone: "info" | "warning" | "danger" }> = {
  not_onboarded: { key: "notOnboarded", tone: "info" },
  pending: { key: "pending", tone: "warning" },
  suspended: { key: "suspended", tone: "danger" },
  rejected: { key: "rejected", tone: "danger" },
};

export function AccountStatusScreen() {
  const t = useT();
  const router = useRouter();
  const raw = useSearchParams().get("reason") as StatusReason | null;
  const reason = REASONS[raw ?? ""] ?? REASONS.not_onboarded;
  const [busy, setBusy] = useState(false);
  const mode = useAuthMode().mode;
  const review = useApi((s) => getOnboardingState(s), "account-status-review", mode === "neon" && (reason.key === "suspended" || reason.key === "rejected"));
  const rejected = review.data && (review.data.decision === "REJECTED" || review.data.decision === "SUSPENDED") ? review.data : null;

  async function onSignOut() {
    setBusy(true);
    await signOutEverywhere();
    router.replace("/login");
  }

  return (
    <AuthShell title={t("auth.status.title")} neonOnly>
      <div className="space-y-4">
        <Alert tone={reason.tone} title={t(`auth.status.${reason.key}.title`)}>
          {t(`auth.status.${reason.key}.body`)}
        </Alert>
        {rejected ? (
          <Alert tone="danger" title={t("auth.status.rejected.title")}>
            {rejected.reason ?? t("auth.status.rejected.noReason")}
          </Alert>
        ) : null}
        {reason.key === "notOnboarded" ? (
          <Link href="/onboarding" className={authLinkClass}>
            {t("ob.continueSetup")}
          </Link>
        ) : null}
        <Button variant="secondary" onClick={onSignOut} loading={busy}>
          {busy ? t("auth.status.signingOut") : t("auth.status.signOut")}
        </Button>
      </div>
    </AuthShell>
  );
}
