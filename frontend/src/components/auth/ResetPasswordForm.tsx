"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getAuthClient } from "@/lib/auth/client";
import { attempt, authErrorKey } from "@/lib/auth/flow";

import { authLinkClass } from "./AuthShell";
import { PasswordStrength } from "./PasswordStrength";

export function ResetPasswordForm() {
  const t = useT();
  const token = useSearchParams().get("token");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const mismatch = confirm !== "" && confirm !== password;

  if (!token) {
    return (
      <div className="space-y-3">
        <Alert tone="warning" urgent>{t("auth.reset.missingToken")}</Alert>
        <Link href="/forgot-password" className={authLinkClass}>
          {t("auth.reset.requestNew")}
        </Link>
      </div>
    );
  }
  if (done) {
    return (
      <div className="space-y-3">
        <Alert tone="success">{t("auth.reset.done")}</Alert>
        <Link href="/login" className={authLinkClass}>
          {t("auth.reset.signIn")}
        </Link>
      </div>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setErrorKey(null);
    try {
      const res = await attempt(() => getAuthClient().resetPassword({ newPassword: password, token }));
      if (res.error) setErrorKey(authErrorKey(res.error, "reset"));
      else setDone(true);
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
      <div>
        <label htmlFor="reset-password" className="mb-1 block text-sm font-medium text-ink">
          {t("auth.reset.password")}
        </label>
        <input id="reset-password" type="password" autoComplete="new-password" required minLength={8}
          aria-describedby="reset-password-strength" value={password}
          onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        <PasswordStrength id="reset-password-strength" password={password} />
      </div>
      <FormField id="reset-confirm" label={t("auth.reset.confirm")} error={mismatch ? t("auth.reset.mismatch") : null}>
        {(aria) => (
          <input {...aria} type="password" autoComplete="new-password" required value={confirm}
            onChange={(e) => setConfirm(e.target.value)} className={inputClass} />
        )}
      </FormField>
      <Button type="submit" loading={busy} disabled={password.length < 8 || password !== confirm}>
        {busy ? t("auth.reset.submitting") : t("auth.reset.submit")}
      </Button>
    </form>
  );
}
