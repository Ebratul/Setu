"use client";

import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import { type DocumentRegistry } from "@/lib/api/registry";
import { formatDate } from "@/lib/format";

/** Pure presentation of one document's registry state. */
export function RegistryBox({ registry }: { registry: DocumentRegistry }) {
  const t = useT();
  const { lang } = useLang();
  const r = registry;
  const date = r.registered_on ? formatDate(r.registered_on.slice(0, 10), lang) : "";
  const purpose = r.purpose ? t(`reg.purposeLower.${r.purpose}`) : "";
  const vars = { date, purpose, lender: r.lender_name ?? "" };
  const lender = Boolean(r.lender_name);

  let tone = "border-line bg-surface-alt text-ink";
  let icon = "○";
  let text = t("reg.box.notRegistered");
  if (r.state === "REGISTERED") {
    tone = "border-success bg-success-soft text-ink";
    icon = "✓";
    text = t(lender ? "reg.box.registeredWith" : "reg.box.registered", vars);
  } else if (r.state === "DUPLICATE") {
    tone = "border-danger bg-danger-soft text-ink";
    icon = "✕";
    const kind = r.result === "NEAR_DUPLICATE" ? "dupNear" : "dupExact";
    text = t(`reg.box.${kind}${lender ? "With" : ""}`, vars);
  }
  return (
    <Card as="section" labelledBy="reg-h" className="space-y-3">
      <h2 id="reg-h" className="text-lg font-bold text-ink">
        {t("reg.box.title")}
      </h2>
      <p
        data-testid="registry-box"
        data-state={r.state}
        className={`flex items-start gap-2 rounded-xl border p-3 text-sm font-semibold ${tone}`}
      >
        <span aria-hidden="true">{icon}</span>
        <span>
          <span className="sr-only">{t(`reg.state.${r.state}`)}: </span>
          {text}
        </span>
      </p>
    </Card>
  );
}
