"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { totpEnable, totpSetup, type TotpSetup } from "@/lib/api/account";
import { apiErrorText } from "@/lib/api/formErrors";
import { isValidTotp } from "@/lib/onboarding/validate";
import { qrPngDataUrl } from "@/lib/qr";

import { RecoveryCodes } from "./RecoveryCodes";

type Props = { onComplete: () => void; onCancel?: () => void };

function spaced(secret: string) {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

export function TotpEnroll({ onComplete, onCancel }: Props) {
  const t = useT();
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const s = await totpSetup();
      setSetup(s);
      setQr(await qrPngDataUrl(s.otpauth_uri, 256).catch(() => null));
    } catch (e) {
      setError(apiErrorText(e, t, "tp.err"));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!setup) return;
    document.getElementById("tp-code")?.focus();
  }, [setup]);

  async function enable() {
    if (!isValidTotp(code)) {
      setError(t("ob.v.code6"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await totpEnable(code.trim());
      setCodes(res.recovery_codes);
    } catch (e) {
      setError(apiErrorText(e, t, "tp.err"));
    } finally {
      setBusy(false);
    }
  }

  if (codes) return <RecoveryCodes codes={codes} onConfirmed={onComplete} />;

  if (!setup) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">{t("tp.lead")}</p>
        {error ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void start()} loading={busy}>
            {t("tp.start")}
          </Button>
          {onCancel ? (
            <Button variant="secondary" onClick={onCancel}>
              {t("common.cancel")}
            </Button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void enable();
      }}
    >
      <ol className="list-decimal space-y-2 pl-5 text-sm text-ink">
        <li>{t("tp.step1")}</li>
        <li>{t("tp.step2")}</li>
        <li>{t("tp.step3")}</li>
      </ol>
      <div className="flex flex-wrap items-start gap-4">
        {qr ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={qr} alt={t("tp.qrAlt")} width={192} height={192} className="rounded-xl border border-line" />
        ) : null}
        <div className="min-w-0 space-y-2 text-sm">
          <p className="text-muted">{t("tp.secretLabel")}</p>
          <p className="font-mono text-base font-bold break-all text-ink" data-testid="totp-secret">
            {spaced(setup.secret)}
          </p>
          <p className="text-xs text-muted">{t("tp.secretOnce")}</p>
          <details className="text-xs text-muted">
            <summary className="min-h-11 cursor-pointer py-2 font-semibold text-brand-text">{t("tp.uri")}</summary>
            <p className="font-mono break-all">{setup.otpauth_uri}</p>
          </details>
        </div>
      </div>
      <FormField id="tp-code" label={`${t("tp.code")} *`} error={error}>
        {(aria) => (
          <input
            {...aria}
            aria-required
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            className={`${inputClass} min-h-11 max-w-48 font-mono tracking-widest`}
          />
        )}
      </FormField>
      <Button type="submit" loading={busy}>
        {t("tp.enable")}
      </Button>
    </form>
  );
}
