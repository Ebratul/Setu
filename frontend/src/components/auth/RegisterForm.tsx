"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { getAuthClient } from "@/lib/auth/client";
import { attempt, authErrorKey } from "@/lib/auth/flow";

import { authLinkClass } from "./AuthShell";
import { PasswordStrength } from "./PasswordStrength";

export function RegisterForm() {
  const t = useT();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrorKey(null);
    try {
      const auth = getAuthClient();
      const res = await attempt(() => auth.signUp.email({ name, email, password }));
      if (res.error) {
        setErrorKey(authErrorKey(res.error));
        return;
      }
      const sent = await attempt(() => auth.emailOtp.sendVerificationOtp({ email, type: "email-verification" }));
      if (sent.error) {
        setErrorKey(authErrorKey(sent.error));
        return;
      }
      router.replace(`/verify-email?${new URLSearchParams({ email }).toString()}`);
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
      <FormField id="reg-name" label={`${t("auth.register.name")} (${t("auth.register.required")})`}>
        {(aria) => (
          <input {...aria} type="text" autoComplete="name" required value={name}
            onChange={(e) => setName(e.target.value)} className={inputClass} />
        )}
      </FormField>
      <FormField id="reg-email" label={`${t("auth.register.email")} (${t("auth.register.required")})`}>
        {(aria) => (
          <input {...aria} type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        )}
      </FormField>
      <div>
        <label htmlFor="reg-password" className="mb-1 block text-sm font-medium text-ink">
          {`${t("auth.register.password")} (${t("auth.register.required")})`}
        </label>
        <input
          id="reg-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          aria-describedby="reg-password-strength"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputClass}
        />
        <PasswordStrength id="reg-password-strength" password={password} />
      </div>
      <Button type="submit" loading={busy} disabled={!name || !email || password.length < 8}>
        {busy ? t("auth.register.submitting") : t("auth.register.submit")}
      </Button>
      <p className="text-sm text-muted">
        {t("auth.register.haveAccount")}{" "}
        <Link href="/login" className={authLinkClass}>
          {t("auth.register.signIn")}
        </Link>
      </p>
      <p className="text-sm text-muted">
        {t("lg.demoHint")}{" "}
        <Link href="/login#lg-demo-h" className={authLinkClass}>
          {t("lg.demoGo")}
        </Link>
      </p>
    </form>
  );
}
