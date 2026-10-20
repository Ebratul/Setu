"use client";

import Link from "next/link";
import { useState } from "react";

import { CopyChip } from "@/components/approvals/CopyChip";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { auditExportUrl, getAuditSummary, verifyAuditNow, type AuditVerify } from "@/lib/api/audit";
import { useApi } from "@/lib/useApi";

import { fmtTime, reasonKey } from "./auditText";

function Bars({ rows, label }: { rows: { key: string; count: number }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <ul aria-label={label} className="space-y-1.5">
      {rows.map((r) => (
        <li key={r.key} className="grid grid-cols-[minmax(0,11rem)_1fr_auto] items-center gap-2 text-xs">
          <span className="truncate font-mono text-ink" title={r.key}>
            {r.key}
          </span>
          <span aria-hidden="true" className="h-2.5 rounded-full bg-surface-alt">
            <span className="block h-full rounded-full bg-brand-600" style={{ width: `${Math.max(3, (r.count / max) * 100)}%` }} />
          </span>
          <span className="font-semibold text-ink">{r.count}</span>
        </li>
      ))}
    </ul>
  );
}

export function EvidenceDashboard() {
  const t = useT();
  const { lang } = useLang();
  const q = useApi((s) => getAuditSummary(s), "audit-summary");
  const [fresh, setFresh] = useState<AuditVerify | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<unknown>(null);

  async function verifyNow() {
    setVerifying(true);
    setVerifyError(null);
    try {
      setFresh(await verifyAuditNow());
    } catch (e) {
      setVerifyError(e);
    } finally {
      setVerifying(false);
    }
  }

  if (q.error) return <QueryError error={q.error} onRetry={q.reload} />;
  const s = q.data;
  if (!s) return <Skeleton className="h-48" />;
  const v = fresh ?? s.last_verification;
  return (
    <section aria-labelledby="ev-h" className="space-y-3" data-testid="evidence">
      <h2 id="ev-h" className="text-lg font-bold text-ink">
        {t("audit.evidence.title")}
      </h2>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="space-y-1">
          <p className="text-sm text-muted">{t("audit.evidence.total")}</p>
          <p className="text-3xl font-bold text-ink" data-testid="audit-total">
            {s.total}
          </p>
          <p className="text-xs text-muted">{t("audit.evidence.head", { seq: s.head_seq })}</p>
          <div className="pt-3">
            <h3 className="mb-1 text-sm font-semibold text-ink">{t("audit.evidence.byTier")}</h3>
            <Bars rows={s.by_tier} label={t("audit.evidence.byTier")} />
          </div>
        </Card>
        <Card className="space-y-2">
          <h3 className="text-sm font-semibold text-ink">{t("audit.evidence.byAction")}</h3>
          <Bars rows={s.by_action.slice(0, 12)} label={t("audit.evidence.byAction")} />
        </Card>
        <Card className="space-y-3">
          <h3 className="text-sm font-semibold text-ink">{t("audit.evidence.lastVerify")}</h3>
          <div aria-live="polite" data-testid="verify-status">
            {v ? (
              v.ok ? (
                <Badge tone="success" icon="✓">
                  {t("audit.evidence.ok", { n: v.entries_checked })}
                </Badge>
              ) : (
                <Badge tone="danger" icon="✕">
                  {t("audit.result.broken", { seq: v.broken_seq ?? "?", reason: t(reasonKey(v.reason)) })}
                </Badge>
              )
            ) : (
              <p className="text-sm text-muted">{t("audit.evidence.never")}</p>
            )}
            {v ? <p className="mt-1 text-xs text-muted">{fmtTime(v.verified_at, lang)}</p> : null}
          </div>
          {verifyError ? <QueryError error={verifyError} onRetry={() => void verifyNow()} /> : null}
          <Button onClick={() => void verifyNow()} disabled={verifying}>
            {verifying ? t("audit.evidence.verifying") : t("audit.evidence.verifyNow")}
          </Button>
          <div className="space-y-1 border-t border-line pt-3">
            <p className="text-xs font-semibold text-muted">{t("audit.evidence.fingerprint")}</p>
            <CopyChip
              text={`${s.fingerprint.slice(0, 16)}…${s.fingerprint.slice(-6)}`}
              copyValue={s.fingerprint}
              ariaLabel={t("audit.evidence.copyFingerprint")}
              copiedLabel={t("audit.copied")}
              testId="fingerprint-copy"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <a
              href={auditExportUrl()}
              download
              className="inline-flex rounded-xl border border-line bg-surface px-4 py-2 text-sm font-semibold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("audit.evidence.export")}
            </a>
            <Link
              href="/verify"
              className="text-sm font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("audit.evidence.verifyLink")}
            </Link>
          </div>
        </Card>
      </div>
    </section>
  );
}
