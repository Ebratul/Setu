"use client";

import { Suspense } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";
import { useT } from "@/i18n";

export default function ResetPage() {
  const t = useT();
  return (
    <AuthShell title={t("auth.reset.title")} lead={t("auth.reset.lead")} neonOnly>
      <Suspense>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
