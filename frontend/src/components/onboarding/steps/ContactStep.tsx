"use client";

import { useEffect, useState } from "react";

import { Field } from "@/components/onboarding/Field";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useLang, useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { apiErrorText } from "@/lib/api/formErrors";
import { saveContact, sendPhoneCode, verifyPhoneCode, type Lang, type PhoneSent } from "@/lib/api/onboarding";
import { serverFieldErrors } from "@/lib/onboarding/errors";
import { isValidTotp, toContactBody, validateContact, type Errors, type FieldDef, type Values } from "@/lib/onboarding/validate";

import type { StepProps } from "./types";

const DEFS: Record<string, FieldDef> = {
  full_name: { key: "full_name", kind: "text", required: true, max: 120, autoComplete: "name" },
  designation: { key: "designation", kind: "text", required: true, max: 80, autoComplete: "organization-title" },
  mobile: { key: "mobile", kind: "text", required: true, max: 20, inputMode: "tel", autoComplete: "tel" },
};
const LANGS: Lang[] = ["en", "bn", "zh"];

export function ContactStep({ state, onState, onNext }: StepProps) {
  const t = useT();
  const { lang } = useLang();
  const c = state.contact;
  const saved = Boolean(c?.mobile_masked);
  const [editing, setEditing] = useState(!saved);
  const [v, setV] = useState<Values>({ full_name: c?.full_name ?? "", designation: c?.designation ?? "", mobile: "" });
  const [language, setLanguage] = useState<Lang>(c?.language ?? lang);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [sent, setSent] = useState<PhoneSent | null>(null);
  const [code, setCode] = useState("");
  const [otpError, setOtpError] = useState<string | null>(null);
  const [otpBusy, setOtpBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  const set = (k: string) => (val: string) => {
    setV((x) => ({ ...x, [k]: val }));
    setErrors((e) => {
      const { [k]: _gone, ...rest } = e;
      void _gone;
      return rest;
    });
  };

  async function save() {
    const errs = validateContact(v, state.role);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      onState(await saveContact(toContactBody(v, language)));
      setEditing(false);
      setSent(null);
      setCode("");
    } catch (e) {
      setErrors(serverFieldErrors(e, Object.keys(DEFS)));
      setError(apiErrorText(e, t, "ob.err"));
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    setOtpBusy(true);
    setOtpError(null);
    try {
      const res = await sendPhoneCode();
      setSent(res);
      setCooldown(30);
    } catch (e) {
      if (e instanceof ApiError && e.retryAfter) setCooldown(e.retryAfter);
      setOtpError(apiErrorText(e, t, "ob.err"));
    } finally {
      setOtpBusy(false);
    }
  }

  async function verify() {
    if (!isValidTotp(code)) {
      setOtpError(t("ob.v.code6"));
      return;
    }
    setOtpBusy(true);
    setOtpError(null);
    try {
      onState(await verifyPhoneCode(code.trim()));
    } catch (e) {
      setOtpError(apiErrorText(e, t, "ob.err"));
    } finally {
      setOtpBusy(false);
    }
  }

  const verified = Boolean(c?.phone_verified);

  if (!editing) {
    return (
      <div className="space-y-5">
        <dl className="grid gap-x-6 gap-y-2 rounded-card border border-line bg-surface p-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted">{t("ob.f.full_name")}</dt>
            <dd className="font-medium text-ink">{c?.full_name}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("ob.f.designation")}</dt>
            <dd className="font-medium text-ink">{c?.designation}</dd>
          </div>
          <div>
            <dt className="text-muted">{t("ob.f.mobile")}</dt>
            <dd className="font-mono font-medium text-ink">{c?.mobile_masked}</dd>
          </div>
        </dl>
        <section aria-labelledby="ob-phone-h" className="space-y-3">
          <h3 id="ob-phone-h" className="font-bold text-ink">
            {t("ob.phone.title")}
          </h3>
          {verified ? (
            <Alert tone="success">{t("ob.phone.verified")}</Alert>
          ) : (
            <>
              <p className="text-sm text-muted">{t("ob.phone.lead", { phone: c?.mobile_masked ?? "" })}</p>
              <Button variant="secondary" onClick={() => void send()} loading={otpBusy && !sent} disabled={cooldown > 0 || otpBusy}>
                {cooldown > 0 ? t("ob.phone.resendIn", { s: cooldown }) : sent ? t("ob.phone.resend") : t("ob.phone.send")}
              </Button>
              {sent ? (
                <div className="space-y-3">
                  <p className="text-sm text-muted">{t("ob.phone.sent", { left: sent.sends_left })}</p>
                  {sent.demo_code ? (
                    <Alert tone="warning" title={t("ob.phone.demoTitle")}>
                      <span>{t("ob.phone.demoBody")} </span>
                      <span className="font-mono text-lg font-bold" data-testid="demo-code">
                        {sent.demo_code}
                      </span>
                    </Alert>
                  ) : null}
                  <form
                    noValidate
                    className="space-y-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void verify();
                    }}
                  >
                    <FormField id="ob-otp" label={`${t("ob.phone.code")} *`} error={otpError}>
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
                    <Button type="submit" loading={otpBusy}>
                      {t("ob.phone.verify")}
                    </Button>
                  </form>
                </div>
              ) : otpError ? (
                <p role="alert" className="text-sm font-medium text-danger">
                  {otpError}
                </p>
              ) : null}
            </>
          )}
        </section>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => setEditing(true)}>
            {t("ob.contact.edit")}
          </Button>
          <Button onClick={() => onNext()} disabled={!verified}>
            {t("ob.next")}
          </Button>
        </div>
        {!verified ? <p className="text-xs text-muted">{t("ob.phone.needed")}</p> : null}
      </div>
    );
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      {error ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
      <Field def={DEFS.full_name} value={v.full_name} error={errors.full_name} onChange={set("full_name")} />
      <Field def={DEFS.designation} value={v.designation} error={errors.designation} onChange={set("designation")} />
      <div>
        <Field def={DEFS.mobile} value={v.mobile} error={errors.mobile} onChange={set("mobile")} />
        <p className="mt-1 text-xs text-muted">{state.role === "SUPPLIER" ? t("ob.mobile.hintIntl") : t("ob.mobile.hint")}</p>
      </div>
      <FormField id="ob-language" label={t("ob.f.language")}>
        {(aria) => (
          <select {...aria} value={language} onChange={(e) => setLanguage(e.target.value as Lang)} className={`${inputClass} min-h-11`}>
            {LANGS.map((l) => (
              <option key={l} value={l}>
                {t(`ob.lang.${l}`)}
              </option>
            ))}
          </select>
        )}
      </FormField>
      <div className="flex flex-wrap gap-2">
        {saved ? (
          <Button variant="secondary" onClick={() => setEditing(false)} disabled={busy}>
            {t("common.cancel")}
          </Button>
        ) : null}
        <Button type="submit" loading={busy}>
          {t("ob.contact.save")}
        </Button>
      </div>
    </form>
  );
}
