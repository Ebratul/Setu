"use client";

import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { hasKey, useT } from "@/i18n";
import type { Review } from "@/lib/api/onboarding";

import { CheckStatusBadge } from "./CheckStatusBadge";
import { RecommendationBadge } from "./RecommendationBadge";

type Props = {
  review: Review;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
};

const SEVERITY = { FAIL: 0, WARN: 1, PASS: 2 } as const;

export function ReviewDetail({ review, onClose, onApprove, onReject }: Props) {
  const t = useT();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [review.id]);
  const p = review.party;
  const bank = review.bank_account;
  const checks = [...review.checks].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  const facts: [string, string][] = [
    [t("onb.f.legalName"), p.legal_name],
    [t("onb.f.accountType"), t(`onb.type.${p.kind === "SUPPLIER" ? "SUPPLIER" : "BUYER"}`)],
    [t("onb.f.licenseName"), p.license_name ?? "-"],
    [t("onb.f.licenseNo"), p.license_no ?? "-"],
    [t("onb.f.taxId"), p.tax_id ?? "-"],
    [t("onb.f.city"), p.city],
    [t("onb.f.country"), p.country],
    [t("adm.onb.applicant"), `${review.user_display_name} (${review.user_email})`],
  ];
  return (
    <Card as="section" labelledBy="rev-h" className="space-y-5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <h2 id="rev-h" ref={heading} tabIndex={-1} className="text-xl font-bold break-words text-ink focus:outline-none">
            {p.legal_name}
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <RecommendationBadge value={review.recommendation} />
            <span className="text-sm text-muted">
              {t("adm.onb.score")}: {review.score}
            </span>
          </div>
        </div>
        <Button variant="secondary" size="sm" onClick={onClose}>
          {t("common.close")}
        </Button>
      </div>

      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {facts.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-muted">{k}</dt>
            <dd className="font-medium break-words text-ink">{v}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="rev-bank-h" className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="rev-bank-h" className="font-bold text-ink">
            {t("adm.onb.bank")}
          </h3>
          <SimulatedBadge />
        </div>
        {bank ? (
          <p className="text-sm text-ink">
            {bank.bank_name} ({bank.bank_country}) · <span className="font-mono">{bank.account_masked}</span> ·{" "}
            {bank.holder_name} · {bank.currency} · {t(`onb.bankType.${bank.account_type}`)}
          </p>
        ) : (
          <p className="text-sm text-muted">{t("adm.onb.noBank")}</p>
        )}
      </section>

      <section aria-labelledby="rev-checks-h" className="space-y-2">
        <h3 id="rev-checks-h" className="font-bold text-ink">
          {t("onb.st.checks")}
        </h3>
        <ul className="divide-y divide-line rounded-card border border-line">
          {checks.map((c) => (
            <li key={c.code} className="flex flex-wrap items-start justify-between gap-2 px-4 py-3 text-sm">
              <div className="min-w-0">
                <p className="font-semibold text-ink">{hasKey(`onb.check.${c.code}`) ? t(`onb.check.${c.code}`) : c.code}</p>
                <p className="break-words text-muted">{c.detail}</p>
              </div>
              <CheckStatusBadge status={c.status} />
            </li>
          ))}
        </ul>
      </section>

      {review.status === "PENDING" ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={onApprove}>{t("adm.onb.approve")}</Button>
          <Button variant="danger" onClick={onReject}>
            {t("adm.onb.reject")}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted">
          {t(`adm.onb.status.${review.status}`)}
          {review.decided_at ? ` · ${review.decided_at.slice(0, 10)}` : ""}
          {review.reason ? ` · ${review.reason}` : ""}
        </p>
      )}
    </Card>
  );
}
