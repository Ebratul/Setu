"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { FormField, inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { apiErrorText } from "@/lib/api/formErrors";
import {
  approveReview,
  listReviews,
  rejectReview,
  type Review,
  type ReviewFilter,
} from "@/lib/api/onboarding";
import { useShellUser } from "@/lib/MeContext";
import { useApi } from "@/lib/useApi";

import { RecommendationBadge } from "./RecommendationBadge";
import { ReviewDetail } from "./ReviewDetail";

export const MIN_REASON = 10;
export const MAX_REASON = 500;

type Tab = ReviewFilter | "ALL";
const TABS: Tab[] = ["PENDING", "APPROVED", "REJECTED", "ALL"];
const STATUS_TONE: Record<ReviewFilter, Tone> = { PENDING: "warning", APPROVED: "success", REJECTED: "danger" };

type Action = { kind: "approve" | "reject"; review: Review };

export function OnboardingQueuePage() {
  const t = useT();
  const me = useShellUser();
  const [tab, setTab] = useState<Tab>("PENDING");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const allowed = me === undefined || me.role === "ADMIN";
  const list = useApi((s) => listReviews(tab === "ALL" ? undefined : tab, s), `onb-queue|${tab}`, allowed);
  const selected = list.data?.items.find((r) => r.id === selectedId) ?? null;

  function open(kind: Action["kind"], review: Review) {
    setAction({ kind, review });
    setReason("");
    setError(null);
  }
  function close() {
    if (!busy) setAction(null);
  }

  async function confirm() {
    if (!action) return;
    setBusy(true);
    setError(null);
    try {
      if (action.kind === "approve") await approveReview(action.review.id);
      else await rejectReview(action.review.id, reason.trim());
      setDone(t(`adm.onb.done.${action.kind}`, { name: action.review.party.legal_name }));
      setAction(null);
      setSelectedId(null);
      list.reload();
    } catch (e) {
      setError(apiErrorText(e, t, "adm.onb.err"));
      if (e instanceof ApiError && e.code === "ONBOARDING_DECIDED") list.reload();
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Review>[] = [
    {
      id: "company",
      header: t("adm.onb.col.company"),
      sortValue: (r) => r.party.legal_name.toLowerCase(),
      cell: (r) => (
        <span className="font-semibold text-ink">
          {r.party.legal_name}
          <span className="block text-xs font-normal text-muted">
            {t(`onb.type.${r.party.kind === "SUPPLIER" ? "SUPPLIER" : "BUYER"}`)} · {r.party.city}, {r.party.country}
          </span>
        </span>
      ),
    },
    {
      id: "applicant",
      header: t("adm.onb.col.applicant"),
      cell: (r) => (
        <span>
          {r.user_display_name}
          <span className="block text-xs text-muted">{r.user_email}</span>
        </span>
      ),
    },
    { id: "rec", header: t("adm.onb.col.recommendation"), cell: (r) => <RecommendationBadge value={r.recommendation} /> },
    {
      id: "status",
      header: t("adm.onb.col.status"),
      cell: (r) => <Badge tone={STATUS_TONE[r.status]}>{t(`adm.onb.status.${r.status}`)}</Badge>,
    },
    {
      id: "submitted",
      header: t("adm.onb.col.submitted"),
      sortValue: (r) => r.submitted_at,
      cell: (r) => r.submitted_at.slice(0, 10),
    },
    {
      id: "open",
      header: t("adm.onb.col.action"),
      cell: (r) => (
        <Button size="sm" variant="secondary" onClick={() => setSelectedId(r.id)} aria-label={`${t("adm.onb.open")}: ${r.party.legal_name}`}>
          {t("adm.onb.open")}
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-ink">{t("adm.onb.title")}</h1>
        <p className="text-muted">{t("adm.onb.intro")}</p>
      </header>

      <div aria-live="polite">{done ? <Alert tone="success">{done}</Alert> : null}</div>

      {!allowed ? (
        <EmptyState title={t("error.noAccessTitle")} body={t("adm.onb.adminOnly")} />
      ) : (
        <Tabs
          label={t("adm.onb.filter")}
          tabs={TABS.map((id) => ({ id, label: t(`adm.onb.tab.${id}`) }))}
          selected={tab}
          onSelect={(id) => {
            setTab(id as Tab);
            setSelectedId(null);
          }}
        >
          <div className="space-y-4" aria-busy={list.loading}>
            {selected ? (
              <ReviewDetail
                review={selected}
                onClose={() => setSelectedId(null)}
                onApprove={() => open("approve", selected)}
                onReject={() => open("reject", selected)}
              />
            ) : null}
            {list.error ? (
              <QueryError error={list.error} onRetry={list.reload} />
            ) : !list.data ? (
              <Skeleton className="h-48" />
            ) : list.data.items.length === 0 ? (
              <EmptyState title={t("adm.onb.empty")} />
            ) : (
              <DataTable caption={t("adm.onb.title")} columns={columns} rows={list.data.items} rowKey={(r) => r.id} />
            )}
          </div>
        </Tabs>
      )}

      {action?.kind === "approve" ? (
        <ConfirmDialog
          title={t("adm.onb.approveTitle")}
          confirmLabel={t("adm.onb.approve")}
          busy={busy}
          error={error}
          onConfirm={() => void confirm()}
          onClose={close}
        >
          <p>{t("adm.onb.approveBody", { name: action.review.party.legal_name })}</p>
        </ConfirmDialog>
      ) : null}
      {action?.kind === "reject" ? (
        <ConfirmDialog
          title={t("adm.onb.rejectTitle")}
          confirmLabel={t("adm.onb.reject")}
          busy={busy}
          error={error}
          confirmDisabled={reason.trim().length < MIN_REASON}
          onConfirm={() => void confirm()}
          onClose={close}
        >
          <p>{t("adm.onb.rejectBody", { name: action.review.party.legal_name })}</p>
          <FormField
            id="adm-reject-reason"
            label={t("adm.onb.reason")}
            hint={t("adm.onb.reasonHint", { min: MIN_REASON })}
          >
            {(aria) => (
              <textarea
                {...aria}
                rows={4}
                maxLength={MAX_REASON}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className={inputClass}
              />
            )}
          </FormField>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
