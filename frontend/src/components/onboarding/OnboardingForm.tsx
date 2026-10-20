"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { authLinkClass, AuthShell } from "@/components/auth/AuthShell";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { Stepper } from "@/components/ui/Stepper";
import { useLang, useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { apiErrorText, fieldErrors } from "@/lib/api/formErrors";
import { getOnboardingStatus, submitOnboarding } from "@/lib/api/onboarding";
import {
  EMPTY_DRAFT,
  FIELD_STEP,
  SERVER_FIELD,
  toInput,
  validateStep,
  type Draft,
  type Errors,
  type FieldKey,
} from "@/lib/onboarding/validate";

const LAST = 3;
const COUNTRIES = ["BD", "CN"] as const;

type TextProps = {
  field: FieldKey;
  label: string;
  draft: Draft;
  errors: Errors;
  set: (k: keyof Draft, v: string) => void;
  hint?: string;
  optional?: boolean;
  autoComplete?: string;
  maxLength?: number;
};

function fieldMessage(errors: Errors, k: FieldKey, t: (key: string, vars?: Record<string, string | number>) => string) {
  const x = errors[k];
  return x ? t(x.key, x.vars) : null;
}

function Text({ field, label, draft, errors, set, hint, optional, autoComplete, maxLength }: TextProps) {
  const t = useT();
  return (
    <FormField
      id={`onb-${field}`}
      label={optional ? `${label} (${t("onb.optional")})` : label}
      error={fieldMessage(errors, field, t)}
      hint={hint}
    >
      {(aria) => (
        <input
          {...aria}
          type="text"
          value={draft[field]}
          autoComplete={autoComplete ?? "off"}
          maxLength={maxLength}
          onChange={(e) => set(field, e.target.value)}
          className={inputClass}
        />
      )}
    </FormField>
  );
}

type SelectProps = Pick<TextProps, "draft" | "errors" | "set"> & {
  field: FieldKey | "language";
  label: string;
  options: { value: string; label: string }[];
};

function Select({ field, label, options, draft, errors, set }: SelectProps) {
  const t = useT();
  return (
    <FormField id={`onb-${field}`} label={label} error={field === "language" ? null : fieldMessage(errors, field, t)}>
      {(aria) => (
        <select {...aria} value={draft[field]} onChange={(e) => set(field, e.target.value)} className={inputClass}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FormField>
  );
}

export function OnboardingForm() {
  const t = useT();
  const router = useRouter();
  const { lang } = useLang();
  const [draft, setDraft] = useState<Draft>({ ...EMPTY_DRAFT, language: lang });
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [exists, setExists] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const first = useRef(true);

  useEffect(() => {
    const ac = new AbortController();
    getOnboardingStatus(ac.signal).then(
      () => router.replace("/onboarding/status"),
      (e: unknown) => {
        if (!ac.signal.aborted && e instanceof ApiError && e.status === 401) {
          router.replace("/login?next=/onboarding");
        }
      },
    );
    return () => ac.abort();
  }, [router]);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    heading.current?.focus();
  }, [step]);

  const set = (k: keyof Draft, v: string) => {
    setDraft((d) => ({ ...d, [k]: v }));
    setErrors((e) => (k in e ? { ...e, [k]: undefined } : e));
  };

  function next() {
    const errs = validateStep(step, draft);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    if (step === 1 && !draft.holderName) setDraft((d) => ({ ...d, holderName: d.legalName.trim() }));
    setStep(step + 1);
  }

  async function submit() {
    for (const s of [0, 1, 2]) {
      const errs = validateStep(s, draft);
      if (Object.keys(errs).length > 0) {
        setErrors(errs);
        setStep(s);
        return;
      }
    }
    setBusy(true);
    setFormError(null);
    try {
      await submitOnboarding(toInput(draft));
      router.replace("/onboarding/status");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        router.replace("/login?next=/onboarding");
        return;
      }
      const server = fieldErrors(e);
      const mapped: Errors = {};
      for (const path of Object.keys(server)) {
        const f = SERVER_FIELD[path];
        if (f) mapped[f] = { key: "onb.v.server" };
      }
      if (Object.keys(mapped).length > 0) {
        setErrors(mapped);
        setStep(Math.min(...Object.keys(mapped).map((k) => FIELD_STEP[k as FieldKey])));
      }
      setExists(e instanceof ApiError && e.code === "ONBOARDING_EXISTS");
      setFormError(apiErrorText(e, t, "onb.err"));
    } finally {
      setBusy(false);
    }
  }

  const err = (k: FieldKey) => fieldMessage(errors, k, t);

  const countryOptions = COUNTRIES.map((c) => ({ value: c, label: t(`onb.country.${c}`) }));
  const steps = [
    { id: "type", label: t("onb.step.type") },
    { id: "company", label: t("onb.step.company") },
    { id: "bank", label: t("onb.step.bank") },
    { id: "review", label: t("onb.step.review") },
  ];

  const summary: [string, string][] = [
    [t("onb.f.accountType"), t(`onb.type.${draft.accountType || "BUYER"}`)],
    [t("onb.f.displayName"), draft.displayName],
    [t("onb.f.legalName"), draft.legalName],
    [t("onb.f.licenseName"), draft.licenseName || "-"],
    [t("onb.f.licenseNo"), draft.licenseNo],
    [t("onb.f.taxId"), draft.taxId],
    [t("onb.f.city"), draft.city],
    [t("onb.f.country"), t(`onb.country.${draft.country}`)],
    [t("onb.f.language"), t(`onb.lang.${draft.language}`)],
    [t("onb.f.bankName"), draft.bankName],
    [t("onb.f.bankCountry"), draft.bankCountry.toUpperCase()],
    [t("onb.f.accountNumber"), `•••• ${draft.accountNumber.trim().slice(-4)}`],
    [t("onb.f.holderName"), draft.holderName],
    [t("onb.f.currency"), draft.currency],
    [t("onb.f.bankAccountType"), t(`onb.bankType.${draft.bankAccountType}`)],
  ];

  const text = { draft, errors, set };
  return (
    <AuthShell title={t("onb.title")} lead={t("onb.lead")} neonOnly>
      <div className="space-y-6">
        <Alert tone="info">{t("onb.notice")}</Alert>
        <Stepper steps={steps} current={step} label={t("onb.steps")} />
        <form
          noValidate
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (step === LAST) void submit();
            else next();
          }}
        >
          <h2 ref={heading} tabIndex={-1} className="text-lg font-bold text-ink focus:outline-none">
            {t(`onb.step.${["type", "company", "bank", "review"][step]}`)}
          </h2>
          <div aria-live="polite">
            {formError ? (
              <p role="alert" className="text-sm font-medium text-danger">
                {formError}{" "}
                {exists ? (
                  <Link href="/onboarding/status" className={authLinkClass}>
                    {t("onb.toStatus")}
                  </Link>
                ) : null}
              </p>
            ) : null}
          </div>

          {step === 0 ? (
            <fieldset className="space-y-4">
              <legend className="sr-only">{t("onb.step.type")}</legend>
              <FormField id="onb-accountType" label={t("onb.f.accountType")} error={err("accountType")}>
                {(aria) => (
                  <select
                    {...aria}
                    value={draft.accountType}
                    onChange={(e) => set("accountType", e.target.value)}
                    className={inputClass}
                  >
                    <option value="">{t("onb.choose")}</option>
                    <option value="BUYER">{t("onb.type.BUYER")}</option>
                    <option value="SUPPLIER">{t("onb.type.SUPPLIER")}</option>
                  </select>
                )}
              </FormField>
              <Text {...text} field="displayName" label={t("onb.f.displayName")} hint={t("onb.h.displayName")} autoComplete="name" maxLength={120} />
              <Select {...text} field="language" label={t("onb.f.language")} options={[
                { value: "en", label: t("onb.lang.en") },
                { value: "bn", label: t("onb.lang.bn") },
                { value: "zh", label: t("onb.lang.zh") },
              ]} />
            </fieldset>
          ) : null}

          {step === 1 ? (
            <fieldset className="space-y-4">
              <legend className="sr-only">{t("onb.step.company")}</legend>
              <Text {...text} field="legalName" label={t("onb.f.legalName")} autoComplete="organization" maxLength={200} />
              <Text {...text} field="licenseName" label={t("onb.f.licenseName")} hint={t("onb.h.licenseName")} optional maxLength={200} />
              <Text {...text} field="licenseNo" label={t("onb.f.licenseNo")} maxLength={64} />
              <Text {...text} field="taxId" label={t("onb.f.taxId")} hint={t("onb.h.taxId")} maxLength={32} />
              <Text {...text} field="city" label={t("onb.f.city")} autoComplete="address-level2" maxLength={80} />
              <Select {...text} field="country" label={t("onb.f.country")} options={countryOptions} />
            </fieldset>
          ) : null}

          {step === 2 ? (
            <fieldset className="space-y-4">
              <legend className="sr-only">{t("onb.step.bank")}</legend>
              <Text {...text} field="bankName" label={t("onb.f.bankName")} maxLength={120} />
              <Text {...text} field="bankCountry" label={t("onb.f.bankCountry")} hint={t("onb.h.bankCountry")} maxLength={2} />
              <Text {...text} field="accountNumber" label={t("onb.f.accountNumber")} hint={t("onb.h.accountNumber")} maxLength={34} />
              <Text {...text} field="holderName" label={t("onb.f.holderName")} hint={t("onb.h.holderName")} maxLength={200} />
              <Select {...text} field="currency" label={t("onb.f.currency")} options={["BDT", "USD", "CNY"].map((c) => ({ value: c, label: c }))} />
              <Select {...text} field="bankAccountType" label={t("onb.f.bankAccountType")} options={[
                { value: "CORPORATE", label: t("onb.bankType.CORPORATE") },
                { value: "PERSONAL", label: t("onb.bankType.PERSONAL") },
              ]} />
            </fieldset>
          ) : null}

          {step === LAST ? (
            <div className="space-y-4">
              <dl className="grid gap-x-6 gap-y-2 rounded-card border border-line bg-surface p-4 text-sm sm:grid-cols-2">
                {summary.map(([k, v]) => (
                  <div key={k} className="min-w-0">
                    <dt className="text-muted">{k}</dt>
                    <dd className="font-medium break-words text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
              <Alert tone="warning">{t("onb.reviewNote")}</Alert>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {step > 0 ? (
              <Button variant="secondary" onClick={() => setStep(step - 1)} disabled={busy}>
                {t("onb.back")}
              </Button>
            ) : null}
            {step < LAST ? (
              <Button type="submit">{t("onb.next")}</Button>
            ) : (
              <Button type="submit" loading={busy}>
                {busy ? t("onb.submitting") : t("onb.submit")}
              </Button>
            )}
          </div>
        </form>
      </div>
    </AuthShell>
  );
}
