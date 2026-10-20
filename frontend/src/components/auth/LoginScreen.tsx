"use client";

import { Suspense } from "react";

import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { useAuthMode } from "@/lib/auth/useAuthMode";

import { AuthShell } from "./AuthShell";
import { LoginPanel } from "./LoginPanel";
import { SignInForm } from "./SignInForm";

export function LoginScreen() {
  const t = useT();
  const { mode } = useAuthMode();
  return (
    <AuthShell
      title={mode === "neon" ? t("auth.signIn.title") : t("login.title")}
      lead={t("auth.signIn.lead")}
    >
      <Suspense fallback={<Skeleton className="h-40" />}>
        {mode === "neon" ? (
          <SignInForm />
        ) : (
          <>
            <p
              role="note"
              className="mb-6 rounded-xl border border-warning bg-warning-soft p-3 text-sm text-ink"
            >
              {t("login.demoOnly")}
            </p>
            <LoginPanel />
          </>
        )}
      </Suspense>
    </AuthShell>
  );
}
