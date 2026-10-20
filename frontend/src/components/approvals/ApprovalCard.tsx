"use client";

import { useState } from "react";

import { InfoTip } from "@/components/docs/InfoTip";
import { TierBadge } from "@/components/risk/TierBadge";
import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getApproval, type Approval } from "@/lib/api/approvals";
import { formatMoney, type Currency } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { secondsLeft } from "./approvalLogic";
import { actionLabel, formatDuration, isEmailOnly, pickLang } from "./approvalText";
import { ApprovalReceipt } from "./ApprovalReceipt";
import { EvidenceSnapshot } from "./EvidenceSnapshot";

type Props = { approval: Approval; fetchedAt: number; now: number; onReview: (a: Approval) => void };

const STATUS_TONE: Record<Approval["status"], Tone> = {
  PENDING: "warning",
  APPROVED: "info",
  EXECUTED: "success",
  REJECTED: "neutral",
  CANCELLED: "neutral",
  EXPIRED: "neutral",
  LOCKED: "danger",
};

export function EvidenceLoader({ id }: { id: string }) {
  const ev = useApi((s) => getApproval(id, s), `appr-ev|${id}`);
  if (ev.error) return <QueryError error={ev.error} onRetry={ev.reload} />;
  if (!ev.data) return <Skeleton className="h-24" />;
  return ev.data.value.evidence ? <EvidenceSnapshot evidence={ev.data.value.evidence} /> : null;
}

export function ApprovalCard({ approval: a, fetchedAt, now, onReview }: Props) {
  const t = useT();
  const { lang } = useLang();
  const [showEvidence, setShowEvidence] = useState(false);
  const pending = a.status === "PENDING";
  const emailOnly = isEmailOnly(a) && pending;
  const left = secondsLeft(a.seconds_to_cooling_off_end, fetchedAt, now);
  const expiresSec = a.expires_at ? Math.round((Date.parse(a.expires_at) - now) / 1000) : null;
  const headingId = `appr-${a.id}`;
  return (
    <Card
      as="article"
      labelledBy={headingId}
      className={`space-y-3 border-2 ${emailOnly ? "border-danger" : "border-line"}`}
    >
      <div data-testid="approval-card" data-action={a.action} data-tier={a.tier} data-status={a.status} className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={headingId} className="text-base font-bold text-ink">
            {actionLabel(a, lang)}
          </h2>
          <TierBadge tier={a.tier} />
          <InfoTip topic="tier" doc="security/permission-tiers#what-it-is" />
          <Badge tone={STATUS_TONE[a.status]}>{t(`appr.status.${a.status}`)}</Badge>
          <SimulatedBadge />
        </div>

        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          {a.deal_reference ? (
            <div>
              <dt className="text-muted">{t("appr.deal")}</dt>
              <dd className="font-semibold text-ink">
                {a.deal_reference}
                {a.milestone_seq ? ` · ${t("appr.milestone", { n: a.milestone_seq })}` : ""}
              </dd>
            </div>
          ) : null}
          {a.supplier_name ? (
            <div className="min-w-0">
              <dt className="text-muted">{t("appr.supplier")}</dt>
              <dd className="font-semibold break-words text-ink">{a.supplier_name}</dd>
            </div>
          ) : null}
          {a.amount && a.currency ? (
            <div>
              <dt className="text-muted">{t("appr.amount")}</dt>
              <dd className="font-semibold text-ink" data-testid="approval-amount" aria-label={`${a.amount} ${a.currency}`}>
                {formatMoney(a.amount, a.currency as Currency, lang)}
              </dd>
            </div>
          ) : null}
        </dl>

        <p className="text-xs text-muted">
          {t("appr.requestedBy", { who: a.requested_by })}
          {a.requested_via ? ` · ${a.requested_via === "email" ? t("appr.viaEmail") : t("appr.via", { via: a.requested_via })}` : ""}
        </p>

        {a.reasons.length > 0 ? (
          <div>
            <h3 className="text-sm font-semibold text-ink">{t("appr.reasons")}</h3>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink">
              {a.reasons.map((r) => (
                <li key={r.code}>{pickLang(lang, r.message, r.message_bn)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {emailOnly ? (
          <p role="alert" data-testid="email-origin-note" className="rounded-xl border-2 border-danger bg-danger-soft p-3 text-sm font-semibold text-ink">
            <span aria-hidden="true">⛔ </span>
            {t("appr.emailOnly")}
          </p>
        ) : null}

        {pending ? (
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink">
            {a.cooling_off_until && a.seconds_to_cooling_off_end != null ? (
              <span data-testid="card-cooling" data-demo="cooling-off">
                <span aria-hidden="true">⏱ </span>
                {left > 0 ? t("appr.coolingLeft", { time: formatDuration(left) }) : t("appr.coolingOver")}
              </span>
            ) : null}
            {expiresSec != null ? (
              <span>
                <span aria-hidden="true">⌛ </span>
                {expiresSec > 0 ? t("appr.expiresIn", { time: formatDuration(expiresSec) }) : t("appr.expired")}
              </span>
            ) : null}
          </p>
        ) : null}

        <div>
          <button
            type="button"
            aria-expanded={showEvidence}
            onClick={() => setShowEvidence((v) => !v)}
            className="rounded-md text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {t("appr.ev.title")}
          </button>
          {showEvidence ? (
            <div className="mt-2">
              <EvidenceLoader id={a.id} />
            </div>
          ) : null}
        </div>

        {a.status === "APPROVED" || a.status === "EXECUTED" ? (
          <div className="flex justify-end">
            <ApprovalReceipt approval={a} />
          </div>
        ) : null}

        {pending ? (
          <div className="flex justify-end">
            <Button onClick={() => onReview(a)} data-testid="review-btn" data-demo="approve-button">
              {t("appr.review")}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
