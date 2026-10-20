"use client";

import { useMemo, useRef, useState } from "react";

import { Field } from "@/components/onboarding/Field";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { apiErrorText } from "@/lib/api/formErrors";
import { saveBusiness } from "@/lib/api/onboarding";
import { serverFieldErrors } from "@/lib/onboarding/errors";
import { draftFromBusiness, fieldsFor, flatten, savedValue, toBusinessBody, validateBusiness, type Errors, type Values } from "@/lib/onboarding/validate";

import type { StepProps } from "./types";

const GROUPS: Record<"BUYER" | "SUPPLIER", { id: string; keys: (k: string) => boolean }[]> = {
  BUYER: [
    { id: "company", keys: (k) => ["legal_name", "trade_name", "trade_license_no", "license_authority", "license_expiry", "irc_no", "tin"].includes(k) },
    { id: "address", keys: (k) => k.startsWith("address.") },
    { id: "trade", keys: (k) => ["business_type", "main_import_goods", "monthly_import_volume"].includes(k) },
  ],
  SUPPLIER: [
    { id: "company", keys: (k) => ["legal_name_en", "legal_name_zh", "uscc", "business_scope", "export_experience_years", "wechat_id", "contact_phone"].includes(k) },
    { id: "address", keys: (k) => k.startsWith("address.") },
    { id: "bank", keys: (k) => k.startsWith("bank.") },
  ],
};

export function BusinessStep({ state, onState, onNext }: StepProps) {
  const t = useT();
  const role = state.role === "SUPPLIER" ? "SUPPLIER" : "BUYER";
  const defs = useMemo(() => fieldsFor(role), [role]);
  const initial = useMemo(() => draftFromBusiness(role, state.business), [role, state.business]);
  const savedFlat = useMemo(() => flatten(state.business), [state.business]);
  const [values, setValues] = useState<Values>(initial.values);
  const [errors, setErrors] = useState<Errors>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const summary = useRef<HTMLDivElement>(null);
  const hasSaved = initial.masked.size > 0 || Object.keys(initial.values).length > 0;

  const set = (key: string) => (val: string) => {
    setDirty(true);
    setValues((x) => ({ ...x, [key]: val }));
    setErrors((e) => {
      if (!(key in e)) return e;
      const next = { ...e };
      delete next[key];
      return next;
    });
  };

  async function save() {
    if (hasSaved && !dirty) {
      onNext();
      return;
    }
    const errs = validateBusiness(role, values, initial.masked);
    setErrors(errs);
    if (Object.keys(errs).length > 0) {
      setError(t("ob.fixErrors", { n: Object.keys(errs).length }));
      summary.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onState(await saveBusiness(toBusinessBody(role, values)));
      onNext();
    } catch (e) {
      const server = serverFieldErrors(e, defs.map((d) => d.key));
      setErrors(server);
      setError(apiErrorText(e, t, "ob.err"));
      summary.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p className="text-sm text-muted">{t(role === "SUPPLIER" ? "ob.biz.leadSupplier" : "ob.biz.leadBuyer")}</p>
      <div ref={summary} tabIndex={-1} className="focus:outline-none" aria-live="polite">
        {error ? (
          <p role="alert" className="text-sm font-medium text-danger">
            {error}
          </p>
        ) : null}
      </div>
      {GROUPS[role].map((g) => (
        <fieldset key={g.id} className="space-y-4">
          <legend className="mb-2 text-base font-bold text-ink">{t(`ob.group.${role}.${g.id}`)}</legend>
          {defs
            .filter((d) => g.keys(d.key))
            .map((d) => (
              <Field
                key={d.key}
                def={d}
                value={values[d.key] ?? ""}
                error={errors[d.key]}
                masked={initial.masked.has(d.key) && !values[d.key] ? (savedValue(savedFlat, d.key) ?? "") : null}
                onChange={set(d.key)}
              />
            ))}
        </fieldset>
      ))}
      <Button type="submit" loading={busy}>
        {hasSaved && !dirty ? t("ob.next") : t("ob.saveContinue")}
      </Button>
    </form>
  );
}
