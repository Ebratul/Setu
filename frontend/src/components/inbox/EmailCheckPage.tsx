"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";
import { checkEmail, getDemoEmail, type EmailCheck } from "@/lib/api/approvals";
import { dealErrorText } from "@/lib/api/dealErrors";
import { useApi } from "@/lib/useApi";

import { EmailBlockCard } from "./EmailBlockCard";

export function EmailCheckPage() {
  const t = useT();
  const demo = useApi((s) => getDemoEmail(s), "demo-email");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EmailCheck | null>(null);

  async function run() {
    if (!text.trim()) {
      setError(t("mail.required"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await checkEmail(text));
    } catch (e) {
      setError(dealErrorText(e, t));
    }
    setBusy(false);
  }

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("mail.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="max-w-3xl text-muted">{t("mail.intro")}</p>
      </header>
      <div className="space-y-3 rounded-card bg-surface p-5 shadow-card">
        <FormField id="email-text" label={t("mail.label")} error={error}>
          {(aria) => (
            <textarea
              {...aria}
              rows={9}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setError(null);
              }}
              placeholder={t("mail.placeholder")}
              className={`${inputClass} font-mono`}
            />
          )}
        </FormField>
        <div className="flex flex-wrap gap-2">
          {demo.data ? (
            <Button
              variant="secondary"
              onClick={() => {
                setText(demo.data ?? "");
                setError(null);
              }}
              data-testid="load-demo-email"
            >
              {t("mail.load")}
            </Button>
          ) : null}
          <Button onClick={run} disabled={busy} data-testid="check-email">
            {busy ? t("mail.checking") : t("mail.check")}
          </Button>
        </div>
      </div>
      <div aria-live="polite">{result ? <EmailBlockCard email={result} /> : null}</div>
    </div>
  );
}
