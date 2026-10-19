"use client";

import Link from "next/link";

import { Badge, type Tone } from "@/components/ui/Badge";
import { KybBadge } from "@/components/kyb/KybBadge";
import { RuleTrace } from "@/components/risk/RuleTrace";
import { useT } from "@/i18n";
import type { DocEvidence, Evidence } from "@/lib/api/approvals";
import type { KybBadgeStatus } from "@/lib/api/kyb";

import { prettyCode } from "./approvalText";
import { CopyChip } from "./CopyChip";

const KYB: KybBadgeStatus[] = ["VERIFIED", "WARNING", "BLOCKED", "PENDING"];
const REG_TONE: Record<DocEvidence["registry"], { tone: Tone; icon: string }> = {
  NEW: { tone: "neutral", icon: "○" },
  REGISTERED: { tone: "success", icon: "✓" },
  DUPLICATE: { tone: "danger", icon: "⚠" },
  UNKNOWN: { tone: "warning", icon: "?" },
};
const linkCls =
  "font-semibold text-brand-700 underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

/** Everything a judge or approver needs on one card (read-only data from the API). */
export function EvidenceSnapshot({ evidence }: { evidence: Evidence }) {
  const t = useT();
  const s = evidence.supplier;
  const kyb = s && (KYB as string[]).includes(s.kyb_status) ? (s.kyb_status as KybBadgeStatus) : "PENDING";
  const regOk = evidence.registry_status === "CLEAR";
  return (
    <section aria-label={t("appr.ev.title")} data-testid="evidence" className="space-y-4 rounded-xl border border-line bg-surface-alt p-4 text-sm">
      <h3 className="text-sm font-bold text-ink">{t("appr.ev.title")}</h3>

      {s ? (
        <div className="space-y-1" data-testid="ev-supplier">
          <p className="flex flex-wrap items-center gap-2 text-ink">
            <strong>{s.name}</strong>
            <KybBadge status={kyb} />
            {s.kyb_score != null ? <span className="text-muted">{t("appr.ev.score", { n: s.kyb_score })}</span> : null}
          </p>
          <p className="text-muted">
            {t("appr.ev.account")}: <span className="font-semibold break-all text-ink">{s.account_label ?? t("appr.ev.noAccount")}</span>
            {s.account_age_days != null ? ` · ${t("appr.ev.accountAge", { n: s.account_age_days })}` : ""}
          </p>
        </div>
      ) : null}

      <div>
        <h4 className="mb-1 font-semibold text-ink">{t("appr.ev.docs")}</h4>
        {evidence.documents.length === 0 ? (
          <p className="text-muted">{t("appr.ev.noDocs")}</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2" data-testid="ev-docs">
            {evidence.documents.map((d) => {
              const r = REG_TONE[d.registry];
              const ok = d.issues.length === 0;
              return (
                <li key={d.id} className="flex gap-2 rounded-xl border border-line bg-surface p-2">
                  <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-lg">
                    📄
                  </span>
                  <div className="min-w-0 space-y-1">
                    <p className="text-xs font-semibold text-muted">{prettyCode(d.doc_type)}</p>
                    <p className="text-sm font-semibold break-all text-ink">{d.file_name}</p>
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge tone={ok ? "success" : "warning"} icon={ok ? "✓" : "▲"}>
                        {prettyCode(d.check_status)}
                      </Badge>
                      <Badge tone={r.tone} icon={r.icon}>
                        {t(`appr.ev.docRegistry.${d.registry}`)}
                      </Badge>
                    </div>
                    {!ok ? <p className="text-xs text-muted">{t("appr.ev.issues", { list: d.issues.map(prettyCode).join(", ") })}</p> : null}
                    <Link href={`/app/documents/${d.id}`} className={`text-xs ${linkCls}`}>
                      {t("appr.ev.open")}
                      <span className="sr-only"> {d.file_name}</span>
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div data-testid="ev-registry">
          <h4 className="mb-1 font-semibold text-ink">{t("appr.ev.registry")}</h4>
          <Badge
            tone={regOk ? "success" : evidence.registry_status === "DUPLICATE_FOUND" ? "danger" : "neutral"}
            icon={regOk ? "✓" : evidence.registry_status === "DUPLICATE_FOUND" ? "⚠" : "–"}
          >
            {t(`appr.ev.registryStatus.${evidence.registry_status}`)}
          </Badge>
        </div>
        <div data-testid="ev-fx">
          <h4 className="mb-1 font-semibold text-ink">{t("appr.ev.fx")}</h4>
          {evidence.fx && evidence.fx.rate ? (
            <p className="text-ink">
              {t("appr.ev.fxLine", { pair: evidence.fx.pair, rate: evidence.fx.rate })}{" "}
              <Badge tone={evidence.fx.locked ? "success" : "warning"} icon={evidence.fx.locked ? "🔒" : "▲"}>
                {t(evidence.fx.locked ? "appr.ev.fxLocked" : "appr.ev.fxNotLocked")}
              </Badge>
            </p>
          ) : (
            <p className="text-muted">{t("appr.ev.noFx")}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <h4 className="font-semibold text-ink">{t("appr.ev.trace")}</h4>
        <RuleTrace trace={evidence.trace} />
      </div>

      <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
        {evidence.audit_seq != null ? (
          <CopyChip
            text={t("appr.ev.audit", { seq: evidence.audit_seq })}
            copyValue={`audit #${evidence.audit_seq}`}
            ariaLabel={t("appr.ev.copyAudit")}
            copiedLabel={t("appr.ev.copied")}
            testId="audit-chip"
          />
        ) : (
          t("appr.ev.noAudit")
        )}
      </p>
    </section>
  );
}
