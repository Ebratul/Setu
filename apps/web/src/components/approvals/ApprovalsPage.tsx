"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { useT } from "@/i18n";
import {
  APPROVALS_CHANGED,
  listApprovals,
  openDemoPhone,
  type ApprovalList,
  type Stamped,
} from "@/lib/api/approvals";
import { useApi } from "@/lib/useApi";
import { useNow } from "@/lib/usePoll";

import { ApprovalCard } from "./ApprovalCard";
import { ApprovalDialog } from "./ApprovalDialog";

async function fetchList(tab: "pending" | "history", s: AbortSignal): Promise<Stamped<ApprovalList>> {
  const value = await listApprovals(tab, s);
  return { value, at: Date.now() };
}

export function ApprovalsPage() {
  const t = useT();
  const focus = useSearchParams().get("focus");
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [openId, setOpenId] = useState<string | null>(focus);
  const list = useApi((s) => fetchList(tab, s), `approvals|${tab}`);
  const now = useNow(1000, tab === "pending");
  const { reload } = list;

  useEffect(() => {
    openDemoPhone();
  }, []);
  useEffect(() => {
    window.addEventListener(APPROVALS_CHANGED, reload);
    return () => window.removeEventListener(APPROVALS_CHANGED, reload);
  }, [reload]);

  const onChanged = useCallback(() => reload(), [reload]);

  return (
    <div className="space-y-5">
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-ink">{t("approvals.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="text-muted">{t("appr.intro")}</p>
      </header>
      <Tabs
        label={t("appr.tabs")}
        selected={tab}
        onSelect={(id) => setTab(id as "pending" | "history")}
        tabs={[
          { id: "pending", label: t("appr.pending") },
          { id: "history", label: t("appr.history") },
        ]}
      >
        {list.error ? (
          <QueryError error={list.error} onRetry={list.reload} />
        ) : !list.data ? (
          <Skeleton className="h-48" />
        ) : list.data.value.items.length === 0 ? (
          <EmptyState title={t(tab === "pending" ? "appr.emptyPending" : "appr.emptyHistory")} />
        ) : (
          <ul className="space-y-4" data-testid="approval-list">
            {list.data.value.items.map((a) => (
              <li key={a.id}>
                <ApprovalCard approval={a} fetchedAt={list.data!.at} now={now} onReview={(x) => setOpenId(x.id)} />
              </li>
            ))}
          </ul>
        )}
      </Tabs>
      {openId ? (
        <ApprovalDialog id={openId} onClose={() => setOpenId(null)} onChanged={onChanged} />
      ) : null}
    </div>
  );
}
