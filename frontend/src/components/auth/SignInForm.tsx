"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getAuthClient } from "@/lib/auth/client";
import { attempt, authErrorKey, classifyApiError, finishSignIn, isUnverified, signOutEverywhere } from "@/lib/auth/flow";

import { authLinkClass } from "./AuthShell";

export function SignInForm() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  function goVerify() {
    const q = new URLSearchParams({ email });
    if (next) q.set("next", next);
    router.replace(`/verify-email?${q.toString()}`);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrorKey(null);
    try {
      const auth = getAuthClient();
      const res = await attempt(() => auth.signIn.email({ email, password }));
      if (res.error) {
        if (isUnverified(res.error)) {
          await attempt(() => auth.emailOtp.sendVerificationOtp({ email, type: "email-verification" }));
          goVerify();
          return;
        }
        setErrorKey(authErrorKey(res.error));
        return;
      }
      try {
        router.replace(await finishSignIn(next));
      } catch (err) {
        const problem = classifyApiError(err);
        if (problem.kind === "unverified") {
          await attempt(() => auth.emailOtp.sendVerificationOtp({ email, type: "email-verification" }));
          goVerify();
        } else if (problem.kind === "status") {
          router.replace(`/account-status?reason=${problem.reason}`);
        } else {
          await signOutEverywhere();
          setErrorKey(problem.key);
        }
      }
    } catch {
      setErrorKey("auth.err.generic");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {params.get("verified") ? <Alert tone="success">{t("auth.signIn.verifiedNote")}</Alert> : null}
      {errorKey ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t(errorKey)}
        </p>
      ) : null}
      <FormField id="signin-email" label={t("auth.signIn.email")}>
        {(aria) => (
          <input
            {...aria}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        )}
      </FormField>
      <FormField id="signin-password" label={t("auth.signIn.password")}>
        {(aria) => (
          <input
            {...aria}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        )}
      </FormField>
      <Button type="submit" loading={busy} disabled={!email || !password}>
        {busy ? t("auth.signIn.submitting") : t("auth.signIn.submit")}
      </Button>
      <p className="flex flex-wrap gap-x-4 text-sm">
        <Link href="/forgot-password" className={authLinkClass}>
          {t("auth.signIn.forgot")}
        </Link>
        <span className="inline-flex min-h-11 items-center text-muted">
          {t("auth.signIn.noAccount")}
          <Link href="/register" className={`${authLinkClass} ml-1`}>
            {t("auth.signIn.register")}
          </Link>
        </span>
      </p>
    </form>
  );
}
