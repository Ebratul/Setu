"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { verifyStepup } from "@/lib/api/auth";
import { apiErrorText } from "@/lib/api/formErrors";
import { isValidTotp } from "@/lib/onboarding/validate";

const RECOVERY = /^[A-Za-z0-9]{5}-[A-Za-z0-9]{5}$/;

type Props = { onToken: (token: string) => void; onClose: () => void };

/** Fresh second factor before a destructive admin decision (authenticator code, or an emailed code). */
export function StepupDialog({ onToken, onClose }: Props) {
  const t = useT();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (!isValidTotp(code) && !RECOVERY.test(code.trim())) {
      setError(t("ob.v.code6"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onToken((await verifyStepup(code.trim())).token);
    } catch (e) {
      setError(apiErrorText(e, t, "vq.err"));
      setBusy(false);
    }
  }

  return (
    <ConfirmDialog title={t("vq.stepup.title")} confirmLabel={t("vq.stepup.confirm")} busy={busy} error={error} confirmDisabled={code.trim().length < 6} onConfirm={() => void confirm()} onClose={onClose}>
      <p>{t("vq.stepup.body")}</p>
      <FormField id="vq-stepup" label={`${t("vq.stepup.code")} *`}>
        {(aria) => (
          <input
            {...aria}
            aria-required
            type="text"
                        autoComplete="one-time-code"
            maxLength={11}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\s/g, ""))}
            className={`${inputClass} min-h-11 max-w-48 font-mono tracking-widest`}
          />
        )}
      </FormField>
    </ConfirmDialog>
  );
}
