"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { signOutEverywhere, type StatusReason } from "@/lib/auth/flow";

import { AuthShell } from "./AuthShell";

const REASONS: Record<string, { key: "notOnboarded" | "pending" | "suspended"; tone: "info" | "warning" | "danger" }> = {
  not_onboarded: { key: "notOnboarded", tone: "info" },
  pending: { key: "pending", tone: "warning" },
  suspended: { key: "suspended", tone: "danger" },
};

export function AccountStatusScreen() {
  const t = useT();
  const router = useRouter();
  const raw = useSearchParams().get("reason") as StatusReason | null;
  const reason = REASONS[raw ?? ""] ?? REASONS.not_onboarded;
  const [busy, setBusy] = useState(false);

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
        <Button variant="secondary" onClick={onSignOut} loading={busy}>
          {busy ? t("auth.status.signingOut") : t("auth.status.signOut")}
        </Button>
      </div>
    </AuthShell>
  );
}
