"use client";

import { useEffect, useRef, useState } from "react";

import { CheckStatusBadge } from "@/components/onboarding/CheckStatusBadge";
import { RecommendationBadge } from "@/components/onboarding/RecommendationBadge";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { hasKey, useT } from "@/i18n";
import type { DocumentOut, RevealableField, ReviewDetail } from "@/lib/api/onboarding";
import { reviewFields } from "@/lib/onboarding/reviewFields";
import { labelKey } from "@/lib/onboarding/errors";

const SEVERITY = { FAIL: 0, WARN: 1, PASS: 2 } as const;
const REVEAL_MS = 30_000;

type Props = {
  review: ReviewDetail;
  revealed: Record<string, string>;
  onHide: (field: string) => void;
  onReveal: (field: RevealableField) => void;
  demoMode: boolean;
  isSelf: boolean;
  onOpenDoc: (doc: DocumentOut) => void;
  onClose: () => void;
  onApprove: () => void;
  onChanges: () => void;
  onReject: () => void;
  onSuspend: () => void;
  onAutoApprove: () => void;
};

export function VerificationDetail(p: Props) {
  const t = useT();
  const { review } = p;
  const heading = useRef<HTMLHeadingElement>(null);
  const [hide] = useState(() => p.onHide);
  useEffect(() => heading.current?.focus(), [review.id]);
  useEffect(() => {
    const open = Object.keys(p.revealed);
    if (open.length === 0) return;
    const id = setTimeout(() => open.forEach(hide), REVEAL_MS);
    return () => clearTimeout(id);
  }, [p.revealed, hide]);

  const name = review.party?.legal_name ?? review.user_display_name;
  const fields = reviewFields(review);
  const status = review.decision === "SUSPENDED" ? "SUSPENDED" : review.status;
  const checks = [...review.checks].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  const open = review.status === "PENDING" && review.account_status !== "SUSPENDED";
  const label = (k: string) => (hasKey(`ob.f.${labelKey(k)}`) ? t(`ob.f.${labelKey(k)}`) : k);

  return (
    <Card as="section" labelledBy="vq-detail-h" className="space-y-5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <h2 id="vq-detail-h" ref={heading} tabIndex={-1} className="text-xl font-bold break-words text-ink focus:outline-none">
            {name}
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{t(`onb.type.${review.role}`)}</Badge>
            <RecommendationBadge value={review.recommendation} />
            <span className="text-sm text-muted">
              {t("adm.onb.score")}: {review.score}
            </span>
          </div>
          <p className="text-sm text-muted">
            {review.user_display_name} ({review.user_email})
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={p.onClose}>
          {t("common.close")}
        </Button>
      </div>

      <section aria-labelledby="vq-fields-h" className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="vq-fields-h" className="font-bold text-ink">
            {t("vq.fields")}
          </h3>
          {review.role === "SUPPLIER" ? <SimulatedBadge /> : null}
        </div>
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {fields.map((f) => {
            const shown = f.reveal ? p.revealed[f.reveal] : undefined;
            return (
              <div key={f.key} className="min-w-0">
                <dt className="text-muted">{label(f.key)}</dt>
                <dd lang={f.key.endsWith("_zh") || f.key.startsWith("address.") && review.role === "SUPPLIER" ? "zh" : undefined} className="flex flex-wrap items-center gap-2 font-medium break-words text-ink">
                  <span className={f.reveal && shown === undefined ? "font-mono" : undefined}>{shown ?? f.value}</span>
                  {f.reveal ? (
                    shown === undefined ? (
                      <Button size="sm" variant="secondary" onClick={() => p.onReveal(f.reveal as RevealableField)} aria-label={`${t("vq.reveal")}: ${label(f.key)}`}>
                        {t("vq.reveal")}
                      </Button>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => p.onHide(f.reveal as string)} aria-label={`${t("vq.hide")}: ${label(f.key)}`}>
                        {t("vq.hide")}
                      </Button>
                    )
                  ) : null}
                </dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section aria-labelledby="vq-docs-h" className="space-y-2">
        <h3 id="vq-docs-h" className="font-bold text-ink">
          {t("vq.docs")}
        </h3>
        {review.documents.length === 0 ? (
          <p className="text-sm text-muted">{t("vq.docs.none")}</p>
        ) : (
          <ul className="divide-y divide-line rounded-card border border-line">
            {review.documents.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span className="min-w-0 break-all text-ink">
                  <span className="font-semibold">{t(`ob.doc.${d.type}`)}</span> · {d.original_name}
                </span>
                <Button size="sm" variant="secondary" onClick={() => p.onOpenDoc(d)} aria-label={`${t("vq.doc.view")}: ${d.original_name}`}>
                  {t("vq.doc.view")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="vq-checks-h" className="space-y-2">
        <h3 id="vq-checks-h" className="font-bold text-ink">
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

      {review.change_requests.length > 0 ? (
        <section aria-labelledby="vq-cr-h" className="space-y-2">
          <h3 id="vq-cr-h" className="font-bold text-ink">
            {t("vq.changes.open")}
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
            {review.change_requests.map((c) => (
              <li key={`${c.target}-${c.note}`}>
                <span className="font-semibold">{c.target}</span>: {c.note}
              </li>
            ))}
          </ul>
        </section>
      ) : null}


      {open ? (
        <div className="space-y-3">
          {p.isSelf ? <Alert tone="warning">{t("vq.self")}</Alert> : null}
          <div className="flex flex-wrap gap-2">
            <Button onClick={p.onApprove} disabled={p.isSelf}>
              {t("adm.onb.approve")}
            </Button>
            <Button variant="secondary" onClick={p.onChanges} disabled={p.isSelf}>
              {t("vq.changes.action")}
            </Button>
            <Button variant="danger" onClick={p.onReject} disabled={p.isSelf}>
              {t("adm.onb.reject")}
            </Button>
            <Button variant="danger" onClick={p.onSuspend} disabled={p.isSelf}>
              {t("vq.suspend")}
            </Button>
          </div>
          {p.demoMode ? (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-warning bg-warning-soft p-3 text-sm">
              <Badge tone="warning">{t("vq.demoOnly")}</Badge>
              <Button size="sm" variant="secondary" onClick={p.onAutoApprove} disabled={p.isSelf}>
                {t("vq.autoApprove")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-muted">
            {t(`vq.status.${status}`)}
            {review.decided_at ? ` · ${review.decided_at.slice(0, 10)}` : ""}
            {review.reason ? ` · ${review.reason}` : ""}
          </p>
          {review.status === "APPROVED" && status !== "SUSPENDED" ? (
            <Button variant="danger" onClick={p.onSuspend} disabled={p.isSelf}>
              {t("vq.suspend")}
            </Button>
          ) : null}
        </div>
      )}
    </Card>
  );
}
