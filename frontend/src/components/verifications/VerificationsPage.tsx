"use client";

import { useState } from "react";

import { RecommendationBadge } from "@/components/onboarding/RecommendationBadge";
import { Alert } from "@/components/ui/Alert";
import { Badge, type Tone } from "@/components/ui/Badge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { inputClass } from "@/components/ui/FormField";
import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tabs } from "@/components/ui/Tabs";
import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { apiErrorText } from "@/lib/api/formErrors";
import {
  approveReview,
  autoApproveReview,
  getOnboardingState,
  getReview,
  listReviews,
  rejectReview,
  requestChanges,
  revealField,
  suspendReview,
  type ChangeItem,
  type DocType,
  type RevealableField,
  type DocumentOut,
  type ReviewDetail as ReviewDetailT,
  type ReviewFilter,
  type ReviewItem,
} from "@/lib/api/onboarding";
import { reviewFields } from "@/lib/onboarding/reviewFields";
import { useShellUser } from "@/lib/MeContext";
import { useApi } from "@/lib/useApi";

import { DocumentViewer } from "./DocumentViewer";
import { ReasonDialog } from "./ReasonDialog";
import { RequestChangesDialog } from "./RequestChangesDialog";
import { StepupDialog } from "./StepupDialog";
import { VerificationDetail } from "./VerificationDetail";

type Tab = ReviewFilter | "ALL";
const TABS: Tab[] = ["PENDING", "CHANGES_REQUESTED", "APPROVED", "REJECTED", "SUSPENDED", "ALL"];
const TONE: Record<ReviewFilter | "SUSPENDED", Tone> = { PENDING: "warning", CHANGES_REQUESTED: "info", APPROVED: "success", REJECTED: "danger", SUSPENDED: "danger" };
const displayStatus = (r: ReviewItem) => (r.decision === "SUSPENDED" ? "SUSPENDED" : r.status);
type Role = "ALL" | "BUYER" | "SUPPLIER";
type Dialog = "approve" | "changes" | "reject" | "suspend" | "auto" | null;
type Decide = (step: string | null) => Promise<unknown>;

export function VerificationsPage() {
  const t = useT();
  const me = useShellUser();
  const [tab, setTab] = useState<Tab>("PENDING");
  const [role, setRole] = useState<Role>("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [revealField_, setRevealField] = useState<RevealableField | null>(null);
  const [viewDoc, setViewDoc] = useState<DocumentOut | null>(null);
  const [stepToken, setStepToken] = useState<string | null>(null);
  const [pendingStep, setPendingStep] = useState<Decide | null>(null);

  const allowed = me === undefined || me.role === "ADMIN";
  const list = useApi((s) => listReviews(tab === "ALL" ? undefined : tab, role === "ALL" ? undefined : role, s), `vq-list|${tab}|${role}`, allowed);
  const detail = useApi((s) => getReview(selectedId ?? "", s), `vq-detail|${selectedId}`, allowed && selectedId !== null);
  const mine = useApi((s) => getOnboardingState(s), "vq-demo-mode", allowed);
  const review: ReviewDetailT | null = selectedId ? (detail.data ?? null) : null;

  function select(id: string | null) {
    setSelectedId(id);
    setRevealed({});
  }
  function closeDialog() {
    if (!busy) {
      setDialog(null);
      setRevealField(null);
      setError(null);
    }
  }

  async function run(fn: Decide, message: string) {
    setBusy(true);
    setError(null);
    try {
      await fn(stepToken);
      setDone(message);
      setDialog(null);
      select(null);
      list.reload();
    } catch (e) {
      if (e instanceof ApiError && (e.code === "STEPUP_REQUIRED" || e.code === "STEPUP_TOTP_REQUIRED")) {
        setPendingStep(() => async (token: string | null) => {
          await fn(token);
          setDone(message);
          setDialog(null);
          select(null);
          list.reload();
        });
        setStepToken(null);
      } else {
        setError(apiErrorText(e, t, "vq.err"));
        if (e instanceof ApiError && e.code === "ONBOARDING_DECIDED") list.reload();
      }
    } finally {
      setBusy(false);
    }
  }

  async function onStepToken(token: string) {
    const retry = pendingStep;
    setStepToken(token);
    setPendingStep(null);
    if (!retry) return;
    setBusy(true);
    try {
      await retry(token);
    } catch (e) {
      setError(apiErrorText(e, t, "vq.err"));
    } finally {
      setBusy(false);
    }
  }

  async function doReveal(reason: string) {
    if (!review || !revealField_) return;
    setBusy(true);
    setError(null);
    try {
      const res = await revealField(review.id, revealField_, reason);
      setRevealed((r) => ({ ...r, [res.field]: res.value }));
      setRevealField(null);
    } catch (e) {
      setError(apiErrorText(e, t, "vq.err"));
    } finally {
      setBusy(false);
    }
  }

  const name = review?.party?.legal_name ?? review?.user_display_name ?? "";
  const columns: Column<ReviewItem>[] = [
    {
      id: "company",
      header: t("adm.onb.col.company"),
      sortValue: (r) => (r.party?.legal_name ?? "").toLowerCase(),
      cell: (r) => (
        <span className="font-semibold text-ink">
          {r.party?.legal_name ?? r.user_display_name}
          <span className="block text-xs font-normal text-muted">{t(`onb.type.${r.role}`)}</span>
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
    { id: "status", header: t("adm.onb.col.status"), cell: (r) => <Badge tone={TONE[displayStatus(r)]}>{t(`vq.status.${displayStatus(r)}`)}</Badge> },
    { id: "submitted", header: t("adm.onb.col.submitted"), sortValue: (r) => r.submitted_at, cell: (r) => r.submitted_at.slice(0, 10) },
    {
      id: "open",
      header: t("adm.onb.col.action"),
      cell: (r) => (
        <Button size="sm" variant="secondary" onClick={() => select(r.id)} aria-label={`${t("adm.onb.open")}: ${r.party?.legal_name ?? r.user_display_name}`}>
          {t("adm.onb.open")}
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-ink">{t("vq.title")}</h1>
        <p className="text-muted">{t("vq.intro")}</p>
      </header>

      <div aria-live="polite">{done ? <Alert tone="success">{done}</Alert> : null}</div>

      {!allowed ? (
        <EmptyState title={t("error.noAccessTitle")} body={t("adm.onb.adminOnly")} />
      ) : (
        <>
          <div className="max-w-xs">
            <label htmlFor="vq-role" className="mb-1 block text-sm font-medium text-ink">
              {t("vq.roleFilter")}
            </label>
            <select id="vq-role" value={role} onChange={(e) => { setRole(e.target.value as Role); select(null); }} className={`${inputClass} min-h-11`}>
              <option value="ALL">{t("vq.role.ALL")}</option>
              <option value="BUYER">{t("onb.type.BUYER")}</option>
              <option value="SUPPLIER">{t("onb.type.SUPPLIER")}</option>
            </select>
          </div>
          <Tabs label={t("adm.onb.filter")} tabs={TABS.map((id) => ({ id, label: t(`vq.tab.${id}`) }))} selected={tab} onSelect={(id) => { setTab(id as Tab); select(null); }}>
            <div className="space-y-4" aria-busy={list.loading}>
              {selectedId ? (
                detail.error ? (
                  <QueryError error={detail.error} onRetry={detail.reload} />
                ) : review ? (
                  <VerificationDetail
                    review={review}
                    demoMode={Boolean(mine.data?.demo_mode)}
                    isSelf={review.user_id === me?.id}
                    revealed={revealed}
                    onHide={(f) => setRevealed((r) => { const n = { ...r }; delete n[f]; return n; })}
                    onReveal={(f) => { setError(null); setRevealField(f); }}
                    onOpenDoc={setViewDoc}
                    onClose={() => select(null)}
                    onApprove={() => setDialog("approve")}
                    onChanges={() => setDialog("changes")}
                    onReject={() => setDialog("reject")}
                    onSuspend={() => setDialog("suspend")}
                    onAutoApprove={() => setDialog("auto")}
                  />
                ) : (
                  <Skeleton className="h-64" />
                )
              ) : null}
              {list.error ? (
                <QueryError error={list.error} onRetry={list.reload} />
              ) : !list.data ? (
                <Skeleton className="h-48" />
              ) : list.data.items.length === 0 ? (
                <EmptyState title={t("adm.onb.empty")} />
              ) : (
                <DataTable caption={t("vq.title")} columns={columns} rows={list.data.items} rowKey={(r) => r.id} />
              )}
            </div>
          </Tabs>
        </>
      )}

      {review && dialog === "approve" ? (
        <ConfirmDialog title={t("adm.onb.approveTitle")} confirmLabel={t("adm.onb.approve")} busy={busy} error={error} onConfirm={() => void run((s) => approveReview(review.id, s), t("vq.done.approve", { name }))} onClose={closeDialog}>
          <p>{t("vq.approveBody", { name })}</p>
        </ConfirmDialog>
      ) : null}
      {review && dialog === "auto" ? (
        <ConfirmDialog title={t("vq.autoApprove")} confirmLabel={t("vq.autoApprove")} busy={busy} error={error} onConfirm={() => void run(() => autoApproveReview(review.id), t("vq.done.approve", { name }))} onClose={closeDialog}>
          <p>{t("vq.autoBody")}</p>
        </ConfirmDialog>
      ) : null}
      {review && dialog === "changes" ? (
        <RequestChangesDialog
          fields={reviewFields(review).map((f) => f.key)}
          docTypes={Array.from(new Set(review.documents.map((d) => d.type))) as DocType[]}
          busy={busy}
          error={error}
          onConfirm={(items: ChangeItem[]) => void run((s) => requestChanges(review.id, items, s), t("vq.done.changes", { name }))}
          onClose={closeDialog}
        />
      ) : null}
      {review && dialog === "reject" ? (
        <ReasonDialog title={t("adm.onb.rejectTitle")} body={t("vq.rejectBody", { name })} confirmLabel={t("adm.onb.reject")} busy={busy} error={error} onConfirm={(reason) => void run((s) => rejectReview(review.id, reason, s), t("vq.done.reject", { name }))} onClose={closeDialog} />
      ) : null}
      {review && dialog === "suspend" ? (
        <ReasonDialog title={t("vq.suspendTitle")} body={t("vq.suspendBody", { name })} confirmLabel={t("vq.suspend")} busy={busy} error={error} onConfirm={(reason) => void run((s) => suspendReview(review.id, reason, s), t("vq.done.suspend", { name }))} onClose={closeDialog} />
      ) : null}
      {review && revealField_ ? (
        <ReasonDialog title={t("vq.revealTitle")} body={t("vq.revealBody")} confirmLabel={t("vq.reveal")} busy={busy} error={error} maxLength={300} onConfirm={(reason) => void doReveal(reason)} onClose={closeDialog} />
      ) : null}
      {review && viewDoc ? <DocumentViewer doc={viewDoc} onClose={() => setViewDoc(null)} /> : null}
      {pendingStep ? <StepupDialog onToken={(tok) => void onStepToken(tok)} onClose={() => setPendingStep(null)} /> : null}
    </div>
  );
}
