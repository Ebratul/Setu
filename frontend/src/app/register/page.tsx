"use client";

import { Suspense } from "react";

import { AuthShell } from "@/components/auth/AuthShell";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { useT } from "@/i18n";

export default function RegisterPage() {
  const t = useT();
  return (
    <AuthShell title={t("auth.register.title")} lead={t("auth.register.lead")} neonOnly>
      <Suspense>
        <RegisterForm />
      </Suspense>
    </AuthShell>
  );
}
