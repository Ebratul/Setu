"use client";

import { Suspense } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { useT } from "@/i18n";

export default function ForgotPage() {
  const t = useT();
  return (
    <AuthShell title={t("auth.forgot.title")} lead={t("auth.forgot.lead")} neonOnly backHref="/login">
      <Suspense>
        <ForgotPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
