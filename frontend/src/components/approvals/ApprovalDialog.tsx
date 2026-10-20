"use client";

import { useEffect, useRef, useState } from "react";

import { TierBadge } from "@/components/risk/TierBadge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { QueryError } from "@/components/ui/QueryError";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import {
  approve,
  cancelApproval,
  getApproval,
  notifyApprovalsChanged,
  openDemoPhone,
  reject,
  resendOtp,
  type Approval,
} from "@/lib/api/approvals";
import { ApiError } from "@/lib/api/client";
import { dealErrorText } from "@/lib/api/dealErrors";
import { formatMoney, type Currency } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { useNow } from "@/lib/usePoll";

import { canSubmitOtp, secondsLeft } from "./approvalLogic";
import { actionLabel, isEmailOnly, pickLang, whatHappens } from "./approvalText";
import { CoolingRing } from "./CoolingRing";
import { EvidenceSnapshot } from "./EvidenceSnapshot";
import { OtpInput } from "./OtpInput";

type Props = { id: string; onClose: () => void; onChanged: () => void };

/** Tier 2 (one tap) and Tier 3 (cooling-off + one-time code) decision dialog. Executes nothing itself: the server does. */
export function ApprovalDialog({ id, onClose, onChanged }: Props) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const [currentId, setCurrentId] = useState(id);
  const detail = useApi((s) => getApproval(currentId, s), `appr|${currentId}`);
  const stamped = detail.data && detail.data.value.id === currentId ? detail.data : undefined;
  const a = stamped?.value;
  const tier3 = a?.tier === 3;
  const open = a?.status === "PENDING";
  const now = useNow(1000, Boolean(tier3 && open));

  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const left = a && stamped ? secondsLeft(a.seconds_to_cooling_off_end, stamped.at, now) : 0;
  const reloadedAt = useRef<number | null>(null);
  const reload = detail.reload;
  useEffect(() => {
    if (!a || !stamped || !tier3 || !open) return;
    if (left === 0 && (a.seconds_to_cooling_off_end ?? 0) > 0 && reloadedAt.current !== stamped.at) {
      reloadedAt.current = stamped.at;
      reload();
    }
  }, [left, a, stamped, tier3, open, reload]);

  useEffect(() => {
    if (tier3) openDemoPhone();
  }, [tier3]);

  const emailOnly = a ? isEmailOnly(a) : false;
  const isLocked = locked || a?.status === "LOCKED";

  async function onApprove() {
    if (!a) return;
    setBusy(true);
    setError(null);
    try {
      const res = await approve(a.id, tier3 ? otp : undefined);
      notifyApprovalsChanged();
      onChanged();
      if (res.outcome === "RE_ESCALATED" && res.new_approval) {
        setNotice(pickLang(lang, res.message_en, res.message_bn) || t("appr.reescalated"));
        setOtp("");
        setCurrentId(res.new_approval.id);
        setBusy(false);
        return;
      }
      const msg = pickLang(lang, res.message_en, res.message_bn);
      toast(
        msg || t(res.outcome === "EXECUTED" ? "appr.executed" : "appr.approvedNotExecuted"),
        res.outcome === "EXECUTED" ? "success" : "info",
      );
      onClose();
    } catch (e) {
      handleError(e);
      setBusy(false);
    }
  }

  function handleError(e: unknown) {
    const code = e instanceof ApiError ? e.code : null;
    if (code === "OTP_INVALID") {
      const n = e instanceof ApiError ? /(\d+)\s+tries/.exec(e.detail ?? "")?.[1] : undefined;
      setError(n ? t("appr.t3.wrong", { n }) : dealErrorText(e, t));
      setOtp("");
    } else if (code === "OTP_LOCKED" || code === "APPROVAL_LOCKED") {
      setLocked(true);
      setError(null);
    } else {
      setError(dealErrorText(e, t));
    }
    reload();
    notifyApprovalsChanged();
    onChanged();
  }

  async function onReject() {
    if (!a) return;
    setBusy(true);
    setError(null);
    try {
      await reject(a.id);
      notifyApprovalsChanged();
      onChanged();
      toast(t("appr.rejected"), "info");
      onClose();
    } catch (e) {
      handleError(e);
      setBusy(false);
    }
  }

  async function onCancel() {
    if (!a) return;
    setBusy(true);
    setError(null);
    try {
      await cancelApproval(a.id);
      notifyApprovalsChanged();
      onChanged();
      toast(t("appr.t3.cancelled"), "info");
      onClose();
    } catch (e) {
      handleError(e);
      setCancelling(false);
      setBusy(false);
    }
  }

  async function onResend() {
    if (!a) return;
    setBusy(true);
    setError(null);
    try {
      await resendOtp(a.id);
      toast(t("appr.t3.resent"), "info");
      setOtp("");
      setLocked(false);
      reload();
    } catch (e) {
      handleError(e);
    }
    setBusy(false);
  }

  const title = a
    ? t(tier3 ? "appr.t3Title" : "appr.t2Title", { action: actionLabel(a, lang) })
    : t("appr.review");
  const submitOk = tier3
    ? canSubmitOtp({ left, code: otp, locked: isLocked, busy })
    : !busy;
  const approveDisabled = !a || !a.can_approve || emailOnly || !submitOk || !open;
  const whyId = "appr-approve-why";

  return (
    <Modal title={title} onClose={onClose} closeDisabled={busy}>
      {detail.error && !a ? (
        <QueryError error={detail.error} onRetry={detail.reload} />
      ) : !a ? (
        <Skeleton className="h-48" />
      ) : (
        <div className="space-y-4 text-sm text-ink" data-testid={tier3 ? "tier3-dialog" : "tier2-dialog"}>
          {notice ? (
            <div role="status" data-testid="reescalated-note" className="rounded-xl border-2 border-warning bg-warning-soft p-3">
              <p className="font-bold">{t("appr.reescalatedTitle")}</p>
              <p>{notice}</p>
            </div>
          ) : null}

          <Summary a={a} />

          {emailOnly && open ? (
            <p role="alert" data-testid="email-origin-note" className="rounded-xl border-2 border-danger bg-danger-soft p-3 font-semibold">
              <span aria-hidden="true">⛔ </span>
              {t("appr.emailOnly")}
            </p>
          ) : null}

          {tier3 && open && !emailOnly ? (
            <div className="space-y-4 rounded-xl border border-line p-3">
              {a.cooling_off_until ? (
                <div className="flex flex-wrap items-center gap-4">
                  <CoolingRing left={left} total={a.cooling_off_total_seconds} />
                  <p className="min-w-0 flex-1 text-sm text-ink" data-testid="why-pause">
                    {pickLang(lang, a.why_pause_en ?? t("appr.t3.pauseDefault"), a.why_pause_bn ?? t("appr.t3.pauseDefault"))}
                  </p>
                </div>
              ) : null}
              <OtpInput
                value={otp}
                onChange={(v) => {
                  setOtp(v);
                  setError(null);
                }}
                label={t("appr.t3.otpLabel")}
                help={a.otp_sent ? `${t("appr.t3.sentHint")} ${t("appr.t3.demoHint")}` : t("appr.t3.demoHint")}
                disabled={busy || isLocked}
                invalid={Boolean(error)}
                describedBy={error ? "appr-otp-err" : undefined}
              />
              {a.otp_attempts_left != null && a.otp_attempts_left < 3 && !isLocked && !error ? (
                <p className="text-xs font-semibold text-danger">{t("appr.t3.wrong", { n: a.otp_attempts_left })}</p>
              ) : null}
              <Button variant="secondary" onClick={onResend} disabled={busy || isLocked} data-testid="resend-otp">
                {t("appr.t3.resend")}
              </Button>
            </div>
          ) : null}

          {isLocked ? (
            <p role="alert" data-testid="otp-locked" className="rounded-xl border-2 border-danger bg-danger-soft p-3 font-semibold text-danger">
              <span aria-hidden="true">🔒 </span>
              {t("appr.t3.locked")}
            </p>
          ) : null}

          {error ? (
            <p id="appr-otp-err" role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 font-medium text-danger">
              {error}
            </p>
          ) : null}

          {a.evidence ? <EvidenceSnapshot evidence={a.evidence} /> : null}

          {cancelling ? (
            <div role="group" aria-label={t("appr.t3.cancel")} className="space-y-2 rounded-xl border-2 border-warning bg-warning-soft p-3">
              <p className="font-semibold">{t("appr.t3.cancelConfirm")}</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={onCancel} disabled={busy} data-testid="cancel-yes">
                  {t("appr.t3.cancelYes")}
                </Button>
                <Button variant="secondary" onClick={() => setCancelling(false)} disabled={busy} autoFocus>
                  {t("appr.t3.cancelNo")}
                </Button>
              </div>
            </div>
          ) : null}

          {open ? (
            <div className="space-y-2">
              {approveDisabled && tier3 && !emailOnly && !isLocked ? (
                <p id={whyId} className="text-xs text-muted">
                  {t("appr.t3.approveWhy")}
                </p>
              ) : null}
              <div className="flex flex-wrap items-center justify-end gap-2">
                {a.can_cancel && !cancelling ? (
                  <Button variant="ghost" onClick={() => setCancelling(true)} disabled={busy} data-testid="cancel-request">
                    {t("appr.t3.cancel")}
                  </Button>
                ) : null}
                <Button variant="secondary" onClick={onReject} disabled={busy || !a.can_reject} data-testid="reject-btn">
                  {t("appr.reject")}
                </Button>
                <Button
                  onClick={onApprove}
                  disabled={approveDisabled}
                  aria-describedby={approveDisabled && tier3 && !emailOnly && !isLocked ? whyId : undefined}
                  data-testid="approve-btn"
                >
                  {busy ? t("common.loading") : t("appr.approve")}
                </Button>
              </div>
            </div>
          ) : (
            <p className="text-sm font-semibold text-muted" role="status">
              {t(`appr.status.${a.status}`)}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}

function Summary({ a }: { a: Approval }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <TierBadge tier={a.tier} />
        <SimulatedBadge />
        {a.amount && a.currency ? (
          <strong className="text-base" aria-label={`${a.amount} ${a.currency}`}>
            {formatMoney(a.amount, a.currency as Currency, lang)}
          </strong>
        ) : null}
        {a.deal_reference ? <span className="text-muted">{a.deal_reference}</span> : null}
        {a.supplier_name ? <span className="text-muted">· {a.supplier_name}</span> : null}
      </div>
      <div className="rounded-xl bg-brand-50 p-3" data-testid="what-happens">
        <p className="text-xs font-bold tracking-wide text-brand-text uppercase">{t("appr.whatHappens")}</p>
        <p className="font-medium">{whatHappens(a, lang)}</p>
      </div>
      {a.reasons.length > 0 ? (
        <div>
          <p className="font-semibold">{t(a.tier === 3 ? "appr.t3.reasonsTitle" : "appr.reasons")}</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {a.reasons.map((r) => (
              <li key={r.code}>{pickLang(lang, r.message, r.message_bn)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {a.tier === 2 ? <p className="text-xs text-muted">{t("appr.tier2Note")}</p> : null}
    </div>
  );
}
