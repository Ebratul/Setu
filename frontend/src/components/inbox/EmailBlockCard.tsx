"use client";

import Link from "next/link";

import { CopyChip } from "@/components/approvals/CopyChip";
import { pickLang } from "@/components/approvals/approvalText";
import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import type { EmailCheck } from "@/lib/api/approvals";

const linkCls =
  "font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

/** Warning card for an email that asks to pay a different account. Icon + text, never colour alone. */
export function EmailBlockCard({ email: e }: { email: EmailCheck }) {
  const t = useT();
  const { lang } = useLang();
  const warn = e.verdict !== "NO_PAYMENT_CHANGE_FOUND";
  const label = e.verdict === "BLOCKED" ? t("mail.blocked") : e.verdict === "SUSPICIOUS" ? t("mail.suspicious") : t("mail.clean");
  const steps = lang === "bn" ? e.next_steps_bn : e.next_steps_en;
  return (
    <Card
      as="section"
      className={`space-y-4 border-2 ${warn ? "border-danger bg-danger-soft" : "border-success bg-success-soft"}`}
    >
      <div role={warn ? "alert" : "status"} data-testid="email-result" data-demo="email-verdict" data-verdict={e.verdict} className="space-y-4">
        <div className="space-y-1">
          <p className="inline-flex items-center gap-2 rounded-full border border-current px-3 py-0.5 text-sm font-bold text-ink">
            <span aria-hidden="true">{e.verdict === "BLOCKED" ? "⛔" : warn ? "⚠" : "✓"}</span>
            {label}
          </p>
          <h2 className="text-lg font-bold text-ink">{warn ? pickLang(lang, e.title_en, e.title_bn) : t("mail.clean")}</h2>
          <p className="text-ink" data-testid="email-message">
            {warn ? pickLang(lang, e.message_en, e.message_bn) : t("mail.cleanBody")}
          </p>
          {e.deal_reference ? <p className="text-sm text-muted">{t("mail.deal", { ref: e.deal_reference })}</p> : null}
        </div>

        {warn ? (
          <p className="font-semibold text-ink" data-testid="account-unchanged">
            <span aria-hidden="true">🛡 </span>
            {t("mail.assurance")}
          </p>
        ) : null}

        {warn ? (
          <div>
            <h3 className="text-sm font-bold text-ink">{t("mail.signals")}</h3>
            {e.signals.length === 0 ? (
              <p className="text-sm text-muted">{t("mail.noSignals")}</p>
            ) : (
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink">
                {e.signals.map((s) => (
                  <li key={s.code}>{pickLang(lang, s.label_en, s.label_bn)}</li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {warn && steps.length > 0 ? (
          <div>
            <h3 className="text-sm font-bold text-ink">{t("mail.next")}</h3>
            <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-sm text-ink">
              {steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 text-sm">
          {e.audit_seq != null ? (
            <CopyChip
              text={t("mail.alert", { seq: e.audit_seq })}
              copyValue={`audit #${e.audit_seq}`}
              ariaLabel={t("appr.ev.copyAudit")}
              copiedLabel={t("appr.ev.copied")}
              testId="alert-chip"
            />
          ) : null}
          {e.related_approval_id ? (
            <Link href={`/app/approvals?focus=${e.related_approval_id}`} className={linkCls} data-testid="related-approval">
              {t("mail.related")}
            </Link>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
