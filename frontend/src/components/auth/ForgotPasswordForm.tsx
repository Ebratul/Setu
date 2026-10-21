"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getAuthClient } from "@/lib/auth/client";
import { attempt, authErrorKey } from "@/lib/auth/flow";

import { authLinkClass } from "./AuthShell";

export function ForgotPasswordForm() {
  const t = useT();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrorKey(null);
    try {
      const res = await attempt(() =>
        getAuthClient().requestPasswordReset({
          email,
          redirectTo: `${window.location.origin}/reset-password`,
        }),
      );
      // Same message whether or not the account exists, so the form cannot be used to probe emails.
      if (res.error && res.error.status === 429) setErrorKey(authErrorKey(res.error));
      else setSent(true);
    } catch {
      setErrorKey("auth.err.generic");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {errorKey ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t(errorKey)}
        </p>
      ) : null}
      {sent ? <Alert tone="success">{t("auth.forgot.sent")}</Alert> : null}
      <FormField id="forgot-email" label={t("auth.forgot.email")}>
        {(aria) => (
          <input {...aria} type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        )}
      </FormField>
      <Button type="submit" loading={busy} disabled={!email}>
        {busy ? t("auth.forgot.submitting") : t("auth.forgot.submit")}
      </Button>
      <p>
        <Link href="/login" className={authLinkClass}>
          {t("auth.forgot.back")}
        </Link>
      </p>
    </form>
  );
}
