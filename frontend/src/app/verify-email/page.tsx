"use client";

import { Suspense } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { VerifyEmailForm } from "@/components/auth/VerifyEmailForm";
import { useT } from "@/i18n";

export default function VerifyPage() {
  const t = useT();
  return (
    <AuthShell title={t("auth.verify.title")} neonOnly backHref="/login">
      <Suspense>
        <VerifyEmailForm />
      </Suspense>
    </AuthShell>
  );
}
