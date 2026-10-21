"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { toneClasses } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useLang, useT } from "@/i18n";
import type { DealCurrency, Milestone } from "@/lib/api/deals";
import { formatDate, formatMoney } from "@/lib/format";

import { EVIDENCE_META, MILESTONE_META, OPEN_STATUSES } from "./milestoneMeta";

type Props = {
  milestones: Milestone[];
  currency: DealCurrency;
  /** Buyer/admin view: show Release controls (with the server's reason when refused). */
  showRelease?: boolean;
  onRelease?: (m: Milestone) => void;
  /** Extra per-milestone controls (dev evidence control). */
  extra?: (m: Milestone) => ReactNode;
};

export function MilestoneStepper({
  milestones,
  currency,
  showRelease = false,
  onRelease,
  extra,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const current = milestones.find((m) => OPEN_STATUSES.includes(m.status));
  const firstUnsettled = milestones.find((m) => !["RELEASED", "REFUNDED", "CANCELLED"].includes(m.status));
  const fmt = (v: string, c: DealCurrency = currency) => formatMoney(v, c, lang);

  return (
    <ol aria-label={t("ms.listLabel")} data-demo="milestone-stepper" className="space-y-3">
      {milestones.map((m) => {
        const meta = MILESTONE_META[m.status];
        const flag = m.can.can_release;
        const settled = ["RELEASED", "REFUNDED", "CANCELLED"].includes(m.status);
        return (
          <li
            key={m.id}
            data-testid="milestone"
            data-status={m.status}
            aria-current={current?.id === m.id ? "step" : undefined}
            className={`rounded-card border-2 bg-surface p-4 shadow-card ${meta.ring}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs font-semibold tracking-wide text-muted uppercase">
                  {t("ms.step", { seq: m.seq })} · {t(`trigger.${m.trigger}`)}
                </p>
                <p className="mt-1 text-lg font-bold text-ink tabular-nums">
                  <span aria-label={`${fmt(m.amount)} ${m.currency}`}>
                    {fmt(m.amount, m.currency)}
                  </span>{" "}
                  <span className="text-sm font-semibold text-muted">
                    ({m.percent_label})
                  </span>
                </p>
              </div>
              <span
                data-testid="milestone-status"
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${toneClasses[meta.tone]}`}
              >
                <span aria-hidden="true">{meta.icon}</span>
                {t(`ms.status.${m.status}`)}
              </span>
            </div>

            <p className="mt-2 text-sm text-ink">{m.condition_text}</p>
            <p className="mt-1 text-xs text-muted">
              {t("ms.due", { date: formatDate(m.due_on, lang) })}
              {m.funded && !settled ? ` · ${t("ms.funded")}` : ""}
            </p>

            <div className="mt-3">
              <p className="text-xs font-semibold text-muted">
                {t("ms.evidence")}:{" "}
                <span data-testid="evidence-status">
                  {t(`ms.ev.${m.evidence_status}`)}
                </span>
              </p>
              <ul data-demo={firstUnsettled?.id === m.id ? "evidence-checklist" : undefined} className="mt-1 space-y-1">
                {m.required_evidence.map((e) => {
                  const em = EVIDENCE_META[e.status];
                  return (
                    <li
                      key={e.doc_type}
                      data-testid="evidence-item"
                      data-status={e.status}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <span
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${toneClasses[em.tone]}`}
                      >
                        <span aria-hidden="true">{em.icon}</span>
                        {t(`ms.ev.${e.status}`)}
                      </span>
                      <span className="text-ink">
                        {t(`docType.${e.doc_type}`)}
                      </span>
                      {e.documents > 0 ? (
                        <span className="text-xs text-muted">
                          {t("ms.docCount", { n: e.documents })}
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>

            {m.settlement && m.settlement.currency !== currency ? (
              <p className="mt-2 text-xs text-muted">
                {t("ms.settlement", {
                  currency: m.settlement.currency,
                  amount: m.settlement.counter_amount
                    ? fmt(m.settlement.counter_amount, m.settlement.currency)
                    : "—",
                  rate: m.settlement.fx_rate ?? "—",
                })}
              </p>
            ) : null}

            {m.status === "PENDING_APPROVAL" ? (
              <p
                data-testid="waiting-approval"
                className="mt-3 rounded-xl border border-warning bg-warning-soft p-2 text-sm text-ink"
              >
                {t("ms.waitingApproval")}{" "}
                <Link
                  href="/app/approvals"
                  className="font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                >
                  {t("ms.openApprovals")}
                </Link>
              </p>
            ) : null}

            {showRelease && !settled && m.status !== "PENDING_APPROVAL" ? (
              <div className="mt-3">
                <Button
                  disabled={!flag.allowed}
                  aria-describedby={flag.allowed ? undefined : `rel-why-${m.id}`}
                  onClick={() => onRelease?.(m)}
                >
                  {t("ms.release")}
                </Button>
                {!flag.allowed && flag.reason ? (
                  <p
                    id={`rel-why-${m.id}`}
                    data-testid="release-reason"
                    className="mt-1 text-xs text-muted"
                  >
                    {flag.reason}
                  </p>
                ) : null}
              </div>
            ) : null}
            {extra?.(m)}
          </li>
        );
      })}
    </ol>
  );
}
