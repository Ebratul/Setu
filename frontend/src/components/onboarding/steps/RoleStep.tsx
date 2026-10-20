"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useT } from "@/i18n";
import { apiErrorText } from "@/lib/api/formErrors";
import { selectRole, type OnboardingRole } from "@/lib/api/onboarding";

import type { StepProps } from "./types";

const ROLES: OnboardingRole[] = ["BUYER", "SUPPLIER", "JUDGE", "ADMIN"];

export function RoleStep({ state, onState, onNext }: StepProps) {
  const t = useT();
  const locked = state.role !== null;
  const [role, setRole] = useState<OnboardingRole | "">(state.role ?? "");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!role) {
      setError(t("ob.v.chooseRole"));
      return;
    }
    if (locked && role === state.role) {
      onNext();
      return;
    }
    if (role === "JUDGE" && !code.trim()) {
      setError(t("ob.v.inviteCode"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await selectRole(role, role === "JUDGE" ? code.trim() : undefined);
      onState(updated);
      onNext(updated);
    } catch (e) {
      setError(apiErrorText(e, t, "ob.err"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <p className="text-sm text-muted">{t("ob.role.lead")}</p>
      <fieldset className="space-y-3" aria-describedby={error ? "ob-role-err" : undefined}>
        <legend className="mb-1 text-sm font-medium text-ink">{t("ob.role.legend")}</legend>
        {ROLES.map((r) => (
          <label
            key={r}
            className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-card border p-4 focus-within:ring-2 focus-within:ring-brand-500 ${
              role === r ? "border-brand-700 bg-brand-50" : "border-line bg-surface"
            } ${locked && r !== state.role ? "cursor-not-allowed opacity-60" : ""}`}
          >
            <input
              type="radio"
              name="ob-role"
              value={r}
              checked={role === r}
              disabled={locked && r !== state.role}
              onChange={() => setRole(r)}
              className="mt-1 size-4"
            />
            <span className="min-w-0">
              <span className="block font-semibold text-ink">{t(`ob.role.${r}`)}</span>
              <span className="block text-sm text-muted">{t(`ob.role.${r}.desc`)}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {role === "JUDGE" && !locked ? (
        <FormField id="ob-invite" label={`${t("ob.role.invite")} *`} hint={t("ob.role.inviteHint")}>
          {(aria) => (
            <input {...aria} aria-required type="text" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} className={`${inputClass} min-h-11`} />
          )}
        </FormField>
      ) : null}
      {error ? (
        <p id="ob-role-err" role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
      <Button type="submit" loading={busy}>
        {t("ob.next")}
      </Button>
    </form>
  );
}
