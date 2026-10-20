"use client";

import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useT } from "@/i18n";
import { listAccountChanges, type AccountChange } from "@/lib/api/approvals";
import { useApi } from "@/lib/useApi";
import { usePoll } from "@/lib/usePoll";

import { Bi } from "./Bi";

const ICON: Record<AccountChange["steps"][number]["state"], { icon: string; cls: string }> = {
  DONE: { icon: "✓", cls: "border-success bg-success-soft text-success" },
  CURRENT: { icon: "⏳", cls: "border-warning bg-warning-soft text-warning" },
  UPCOMING: { icon: "○", cls: "border-line bg-surface-alt text-muted" },
  FAILED: { icon: "✕", cls: "border-danger bg-danger-soft text-danger" },
};

type Props = { dealId: string; refreshKey: number };

/** Four-step status of the supplier's payout-account change requests; refreshes every 5 s. */
export function AccountChangeTracker({ dealId, refreshKey }: Props) {
  const t = useT();
  const list = useApi((s) => listAccountChanges(s), `acct-changes|${refreshKey}`);
  usePoll(list.reload, 5000, true);
  const items = (list.data?.items ?? []).filter((c) => c.deal_id === dealId);
  if (!list.data) return list.error ? null : <Skeleton className="h-24" />;
  if (items.length === 0) return null;
  return (
    <Card as="section" labelledBy="trk-h" className="space-y-4">
      <h2 id="trk-h" className="text-lg font-bold text-ink">
        <Bi k="chg.trackerTitle" />
      </h2>
      <ul className="space-y-4" data-testid="change-tracker">
        {items.map((c) => (
          <li key={`${c.account_id}`} className="space-y-3 rounded-xl border border-line p-3" data-stage={c.stage}>
            <p className="text-sm text-ink">
              <span className="font-semibold break-all">{c.account_label}</span>
            </p>
            <p className="text-sm font-bold text-ink" role="status" data-testid="change-stage">
              <Bi k={`chg.stage.${c.stage}`} />
            </p>
            <ol className="grid gap-2 sm:grid-cols-4">
              {c.steps.map((s) => {
                const m = ICON[s.state];
                return (
                  <li key={s.key} data-state={s.state} className="flex items-center gap-2 text-sm">
                    <span aria-hidden="true" className={`flex size-7 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold ${m.cls}`}>
                      {m.icon}
                    </span>
                    <span>
                      <span className="block font-semibold text-ink">
                        <Bi k={`chg.step.${s.key}`} />
                      </span>
                      <span className="block text-xs text-muted">{t(`chg.state.${s.state}`)}</span>
                    </span>
                  </li>
                );
              })}
            </ol>
          </li>
        ))}
      </ul>
    </Card>
  );
}
