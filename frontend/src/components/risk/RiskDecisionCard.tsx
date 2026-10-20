"use client";

import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { RiskOut } from "@/lib/api/risk";

import { DecidedByCode } from "./DecidedByCode";
import { RiskHints } from "./RiskHints";
import { pick } from "./riskText";
import { RuleTrace } from "./RuleTrace";
import { TierBadge } from "./TierBadge";

type Props = { risk: RiskOut; showApprovalLink?: boolean; showSimulated?: boolean };

export function RiskDecisionCard({ risk, showApprovalLink = false, showSimulated = true }: Props) {
  const t = useT();
  const { lang } = useLang();
  const trace = risk.trace ?? [];
  const blocked = risk.decision === "BLOCK";
  const reasonText = risk.reasons
    .map((code) => {
      const item = trace.find((i) => i.code === code);
      return item ? pick(lang, item.label_en, item.label_bn) : code;
    })
    .join(", ");
  const explanation = pick(lang, risk.explanation_en, risk.explanation_bn);
  return (
    <Card
      as="section"
      className={`space-y-4 border-2 ${blocked ? "border-danger" : "border-line"}`}
    >
      <div data-testid="risk-card" className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-bold text-ink">
            {t(blocked ? "risk.card.blockedTitle" : "risk.card.title")}
          </h2>
          <TierBadge tier={risk.tier} decision={risk.decision} />
          <span className="text-sm font-semibold text-ink" data-testid="risk-decision">
            {t(`risk.decision.${risk.decision}`)}
          </span>
          {showSimulated ? <SimulatedBadge /> : null}
        </div>
        {risk.decision === "REQUIRE_APPROVAL" && showApprovalLink ? (
          <p
            role="status"
            className="rounded-xl border border-warning bg-warning-soft p-3 text-sm font-semibold text-ink"
            data-testid="risk-waiting"
          >
            <span aria-hidden="true">⏳ </span>
            {t("risk.card.waiting", {
              tier: risk.tier,
              reasons: reasonText || t("risk.card.noReasons"),
            })}{" "}
            <Link
              href="/app/approvals"
              className="text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              {t("risk.card.openApprovals")}
            </Link>
          </p>
        ) : null}
        {explanation ? (
          <details open>
            <summary className="cursor-pointer text-sm font-semibold text-ink focus-visible:ring-2 focus-visible:ring-brand-500">
              {t("risk.card.why")}
            </summary>
            <p className="mt-1 text-sm text-muted">{explanation}</p>
          </details>
        ) : null}
        <div className="space-y-2">
          <h3 className="text-sm font-bold text-ink">{t("risk.trace.title")}</h3>
          <RuleTrace trace={trace} />
        </div>
        <RiskHints hints={risk.hints ?? []} />
        <DecidedByCode />
      </div>
    </Card>
  );
}
