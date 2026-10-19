"use client";

import { CopyChip } from "@/components/approvals/CopyChip";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getTimeline, type TimelineStep } from "@/lib/api/approvals";
import { useApi } from "@/lib/useApi";

type Props = { reference: string; signature: string };

const ICON: Record<TimelineStep["state"], { icon: string; cls: string }> = {
  DONE: { icon: "✓", cls: "border-success bg-success-soft text-success" },
  CURRENT: { icon: "⏳", cls: "border-warning bg-warning-soft text-warning" },
  UPCOMING: { icon: "○", cls: "border-line bg-surface-alt text-muted" },
  FAILED: { icon: "✕", cls: "border-danger bg-danger-soft text-danger" },
};

/** Agent proposed -> risk engine decided -> human approved -> executed, straight from the audit-linked timeline. */
export function ApprovalTrail({ reference, signature }: Props) {
  const t = useT();
  const { lang } = useLang();
  const tl = useApi((s) => getTimeline(reference, s), `trail|${reference}|${signature}`);
  return (
    <Card as="section" labelledBy="trail-h" className="space-y-3">
      <h2 id="trail-h" className="text-base font-bold text-ink">
        {t("trail.title")}
      </h2>
      {tl.error ? (
        <QueryError error={tl.error} onRetry={tl.reload} />
      ) : !tl.data ? (
        <Skeleton className="h-24" />
      ) : tl.data.steps.length === 0 ? (
        <p className="text-sm text-muted">{t("trail.empty")}</p>
      ) : (
        <ol className="space-y-3" data-testid="approval-trail">
          {tl.data.steps.map((s) => {
            const m = ICON[s.state];
            const label = lang === "bn" ? s.label_bn : s.label_en;
            const detail = lang === "bn" ? s.detail_bn : s.detail_en;
            return (
              <li key={s.key} data-testid={`trail-${s.key}`} data-state={s.state} className="flex gap-3">
                <span
                  aria-hidden="true"
                  className={`flex size-8 shrink-0 items-center justify-center rounded-full border-2 text-sm font-bold ${m.cls}`}
                >
                  {m.icon}
                </span>
                <div className="min-w-0 space-y-0.5 text-sm">
                  <p className="font-semibold text-ink">
                    {label} <span className="font-normal text-muted">({t(`trail.state.${s.state}`)})</span>
                  </p>
                  {detail ? <p className="text-muted">{detail}</p> : null}
                  <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    {s.ts ? <time dateTime={s.ts}>{new Date(s.ts).toLocaleString(lang === "bn" ? "bn-BD" : "en-US")}</time> : null}
                    {s.audit_seq != null ? (
                      <CopyChip
                        text={t("trail.audit", { seq: s.audit_seq })}
                        copyValue={`audit #${s.audit_seq}`}
                        ariaLabel={t("trail.copy", { seq: s.audit_seq })}
                        copiedLabel={t("trail.copied")}
                      />
                    ) : null}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
