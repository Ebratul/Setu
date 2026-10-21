"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { hasKey, useT } from "@/i18n";
import { apiErrorText } from "@/lib/api/formErrors";
import { submitProfile } from "@/lib/api/onboarding";
import { labelKey } from "@/lib/onboarding/errors";
import { fieldsFor, flatten, savedValue } from "@/lib/onboarding/validate";

import type { StepProps } from "./types";

type Props = StepProps & {
  onEdit: (step: "contact" | "business" | "documents" | "security") => void;
};

function Section({
  title,
  onEdit,
  editLabel,
  children,
}: {
  title: string;
  onEdit: () => void;
  editLabel: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2 rounded-card border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold text-ink">{title}</h3>
        <Button
          size="sm"
          variant="secondary"
          onClick={onEdit}
          aria-label={`${editLabel}: ${title}`}
        >
          {editLabel}
        </Button>
      </div>
      {children}
    </section>
  );
}

export function ReviewStep({ state, onState, onNext, onEdit }: Props) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const flat = flatten(state.business);
  const role = state.role === "SUPPLIER" ? "SUPPLIER" : "BUYER";
  const admin = state.role === "ADMIN";

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      onState(await submitProfile());
      onNext();
    } catch (e) {
      setError(apiErrorText(e, t, "ob.err"));
    } finally {
      setBusy(false);
    }
  }

  const show = (k: string) => {
    const v = savedValue(flat, k);
    if (v === undefined || v === "") return "-";
    const opt = `ob.o.${labelKey(k)}.${v}`;
    return hasKey(opt) ? t(opt) : v;
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">{t("ob.review.lead")}</p>
      {admin ? null : (
        <>
          <Section
            title={t("ob.step.contact")}
            onEdit={() => onEdit("contact")}
            editLabel={t("ob.edit")}
          >
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <Row
                k={t("ob.f.full_name")}
                v={state.contact?.full_name ?? "-"}
              />
              <Row
                k={t("ob.f.designation")}
                v={state.contact?.designation ?? "-"}
              />
              <Row
                k={t("ob.f.mobile")}
                v={`${state.contact?.mobile_masked ?? "-"}${state.contact?.phone_verified ? ` (${t("ob.phone.verifiedShort")})` : ""}`}
              />
            </dl>
          </Section>
          <Section
            title={t("ob.step.business")}
            onEdit={() => onEdit("business")}
            editLabel={t("ob.edit")}
          >
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {fieldsFor(role).map((d) => (
                <Row
                  key={d.key}
                  k={t(`ob.f.${labelKey(d.key)}`)}
                  v={show(d.key)}
                  zh={d.zh}
                />
              ))}
            </dl>
          </Section>
          <Section
            title={t("ob.step.documents")}
            onEdit={() => onEdit("documents")}
            editLabel={t("ob.edit")}
          >
            <ul className="space-y-1 text-sm text-ink">
              {state.documents.map((d) => (
                <li key={d.id}>
                  {t(`ob.doc.${d.type}`)}:{" "}
                  <span className="break-all text-muted">
                    {d.original_name}
                  </span>
                </li>
              ))}
            </ul>
          </Section>
        </>
      )}
      <Section
        title={t("ob.step.security")}
        onEdit={() => onEdit("security")}
        editLabel={t("ob.edit")}
      >
        <p className="text-sm text-ink">
          {t("ob.consent.version", {
            version: state.consent?.terms_version ?? state.terms_version,
          })}{" "}
          · {state.mfa.enabled ? t("ob.totp.on") : t("ob.totp.off")}
        </p>
      </Section>
      <Alert tone="info">{t("ob.review.note")}</Alert>
      {error ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}
      <Button onClick={() => void submit()} loading={busy}>
        {busy ? t("ob.submitting") : t("ob.submit")}
      </Button>
    </div>
  );
}

function Row({ k, v, zh }: { k: string; v: string; zh?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{k}</dt>
      <dd
        lang={zh ? "zh" : undefined}
        className="font-medium break-words text-ink"
      >
        {v}
      </dd>
    </div>
  );
}
