"use client";

import Link from "next/link";
import { useState } from "react";

import { TotpEnroll } from "@/components/account/TotpEnroll";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { apiErrorText } from "@/lib/api/formErrors";
import { saveConsent } from "@/lib/api/onboarding";

import type { StepProps } from "./types";

type Props = StepProps & { onTotpDone: () => void };

export function SecurityStep({ state, onState, onNext, onTotpDone }: Props) {
  const t = useT();
  const admin = state.role === "ADMIN";
  const consented = Boolean(state.consent?.accepted_at);
  const [terms, setTerms] = useState(consented);
  const [privacy, setPrivacy] = useState(consented);
  const [verify, setVerify] = useState(consented);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enrolling, setEnrolling] = useState(false);

  async function save() {
    if (!(terms && privacy && verify)) {
      setError(t("ob.v.consent"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onState(
        await saveConsent({
          terms_version: state.terms_version,
          accept_terms: true,
          accept_privacy: true,
          consent_verification: true,
        }),
      );
      onNext();
    } catch (e) {
      setError(apiErrorText(e, t, "ob.err"));
    } finally {
      setBusy(false);
    }
  }

  const totp = (
    <section aria-labelledby="ob-totp-h" className="space-y-3">
      <h3 id="ob-totp-h" className="text-base font-bold text-ink">
        {t("ob.totp.title")}
      </h3>
      {state.mfa.enabled ? (
        <Alert tone="success">{t("ob.totp.on")}</Alert>
      ) : enrolling || admin ? (
        <TotpEnroll
          onComplete={onTotpDone}
          onCancel={admin ? undefined : () => setEnrolling(false)}
        />
      ) : (
        <>
          <p className="text-sm text-muted">{t("ob.totp.optional")}</p>
          <Button variant="secondary" onClick={() => setEnrolling(true)}>
            {t("ob.totp.setup")}
          </Button>
        </>
      )}
    </section>
  );

  return (
    <div className="space-y-6">
      <form
        noValidate
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset className="space-y-2">
          <legend className="mb-1 text-base font-bold text-ink">
            {t("ob.consent.title")}
          </legend>
          <p className="text-xs text-muted">
            {t("ob.consent.version", { version: state.terms_version })}
          </p>
          <label className="flex min-h-11 items-start gap-3 text-sm text-ink">
            <input
              type="checkbox"
              checked={terms}
              onChange={(e) => setTerms(e.target.checked)}
              className="mt-1 size-4"
            />
            <span>
              {t("ob.consent.terms")}{" "}
              <Link
                href="/terms"
                target="_blank"
                className="font-semibold text-brand-text underline"
              >
                {t("lg.terms")}
              </Link>
            </span>
          </label>
          <label className="flex min-h-11 items-start gap-3 text-sm text-ink">
            <input
              type="checkbox"
              checked={privacy}
              onChange={(e) => setPrivacy(e.target.checked)}
              className="mt-1 size-4"
            />
            <span>
              {t("ob.consent.privacy")}{" "}
              <Link
                href="/privacy"
                target="_blank"
                className="font-semibold text-brand-text underline"
              >
                {t("lg.privacy")}
              </Link>
            </span>
          </label>
          <label className="flex min-h-11 items-start gap-3 text-sm text-ink">
            <input
              type="checkbox"
              checked={verify}
              onChange={(e) => setVerify(e.target.checked)}
              className="mt-1 size-4"
            />
            <span>{t("ob.consent.verify")}</span>
          </label>
        </fieldset>
        {error ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {error}
          </p>
        ) : null}
        {admin && !state.mfa.enabled ? (
          <Alert tone="warning">{t("ob.totp.adminRequired")}</Alert>
        ) : null}
        <Button
          type="submit"
          loading={busy}
          disabled={admin && !state.mfa.enabled}
        >
          {t("ob.saveContinue")}
        </Button>
      </form>
      {totp}
    </div>
  );
}
