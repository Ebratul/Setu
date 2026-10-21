"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getAccessToken, getAuthClient } from "@/lib/auth/client";
import { attempt, authErrorKey, classifyApiError, finishSignIn, statusPath } from "@/lib/auth/flow";

import { authLinkClass } from "./AuthShell";

export function VerifyEmailForm() {
  const t = useT();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [resent, setResent] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrorKey(null);
    setResent(false);
    try {
      const res = await attempt(() => getAuthClient().emailOtp.verifyEmail({ email, otp }));
      if (res.error) {
        setErrorKey(authErrorKey(res.error, "otp"));
        return;
      }
      // Verification may sign the user in; if it did, open the Setu session straight away.
      if ((await getAccessToken({ force: true })) === null) {
        router.replace(`/login?verified=1&email=${encodeURIComponent(email)}`);
        return;
      }
      try {
        router.replace(await finishSignIn(next));
      } catch (err) {
        const problem = classifyApiError(err);
        if (problem.kind === "status") router.replace(statusPath(problem.reason));
        else router.replace("/login?verified=1");
      }
    } catch {
      setErrorKey("auth.err.generic");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setErrorKey(null);
    setResent(false);
    try {
      const res = await attempt(() =>
        getAuthClient().emailOtp.sendVerificationOtp({ email, type: "email-verification" }),
      );
      if (res.error) setErrorKey(authErrorKey(res.error));
      else setResent(true);
    } catch {
      setErrorKey("auth.err.generic");
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <p className="text-sm text-muted">
        {params.get("email") ? t("auth.verify.lead", { email: params.get("email") ?? "" }) : t("auth.verify.noEmail")}
      </p>
      {errorKey ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t(errorKey)}
        </p>
      ) : null}
      {resent ? <Alert tone="success">{t("auth.verify.resent")}</Alert> : null}
      {!params.get("email") ? (
        <FormField id="verify-email" label={t("auth.verify.email")}>
          {(aria) => (
            <input {...aria} type="email" autoComplete="email" required value={email}
              onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          )}
        </FormField>
      ) : null}
      <FormField id="verify-otp" label={t("auth.verify.code")}>
        {(aria) => (
          <input {...aria} type="text" inputMode="numeric" autoComplete="one-time-code" required
            maxLength={8} value={otp} onChange={(e) => setOtp(e.target.value.trim())} className={inputClass} />
        )}
      </FormField>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={busy} disabled={!email || !otp}>
          {busy ? t("auth.verify.submitting") : t("auth.verify.submit")}
        </Button>
        <Button variant="secondary" onClick={resend} disabled={!email || busy}>
          {t("auth.verify.resend")}
        </Button>
      </div>
      <Link href="/login" className={authLinkClass}>
        {t("auth.verify.back")}
      </Link>
    </form>
  );
}
