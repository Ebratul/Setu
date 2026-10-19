import type { components } from "./schema.gen";
import { ApiError, apiGet, apiPost } from "./client";

type S = components["schemas"];
export type Approval = S["app__schemas__approvals__ApprovalOut"];
export type ApprovalList = S["ApprovalList"];
export type ApproveResult = S["ApproveResult"];
export type Evidence = S["EvidenceSnapshot"];
export type DocEvidence = S["DocumentEvidence"];
export type PhoneMessage = S["PhoneMessage"];
export type NotificationEvent = S["EventOut"];
export type Notifications = S["NotificationsOut"];
export type Timeline = S["TimelineOut"];
export type TimelineStep = S["TimelineStep"];
export type EmailCheck = S["EmailCheckOut"];
export type SimulateResult = S["SimulateOut"];
export type SimScenario = S["SimulateOut"]["scenario"];
export type AccountChangeIn = S["AccountChangeIn"];
export type AccountChange = S["AccountChangeRequestOut"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });
const enc = encodeURIComponent;

export const listApprovals = (status: "pending" | "history", signal?: AbortSignal) =>
  apiGet<ApprovalList>(`/approvals?status=${status}`, opts(signal));

/** Detail plus the client clock at fetch time, so countdowns tick from the server's seconds. */
export type Stamped<T> = { value: T; at: number };

export async function getApproval(id: string, signal?: AbortSignal): Promise<Stamped<Approval>> {
  const value = await apiGet<Approval>(`/approvals/${enc(id)}`, opts(signal));
  return { value, at: Date.now() };
}

export const approve = (id: string, otp?: string) =>
  apiPost<ApproveResult>(`/approvals/${enc(id)}/approve`, otp ? { otp } : {});
export const reject = (id: string, reason?: string) =>
  apiPost<{ approval: Approval }>(`/approvals/${enc(id)}/reject`, reason ? { reason } : {});
export const cancelApproval = (id: string) =>
  apiPost<{ approval: Approval }>(`/approvals/${enc(id)}/cancel`);
export const resendOtp = (id: string) =>
  apiPost<{ approval: Approval; delivered_to_demo_phone: boolean }>(`/approvals/${enc(id)}/resend-otp`);

/** null when the demo phone is not available (not demo mode or not the buyer). */
export async function getDemoPhone(signal?: AbortSignal): Promise<PhoneMessage[] | null> {
  try {
    const r = await apiGet<S["DemoPhoneOut"]>("/demo/phone", opts(signal));
    return [...r.messages].sort((a, b) => b.created_at.localeCompare(a.created_at));
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 403 || e.status === 401)) return null;
    throw e;
  }
}

export const getNotifications = (signal?: AbortSignal) =>
  apiGet<Notifications>("/notifications", opts(signal));
export const markNotificationsRead = () => apiPost<{ marked: number }>("/notifications/read");

export const getTimeline = (dealRef: string, signal?: AbortSignal) =>
  apiGet<Timeline>(`/deals/${enc(dealRef)}/timeline`, opts(signal));

export const checkEmail = (text: string, dealReference?: string) =>
  apiPost<EmailCheck>("/inbox/email-check", { text, deal_reference: dealReference || null });

export async function getDemoEmail(signal?: AbortSignal): Promise<string | null> {
  try {
    return (await apiGet<{ text: string }>("/inbox/demo-email", opts(signal))).text;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const simulate = (scenario: SimScenario) =>
  apiPost<SimulateResult>(`/demo/simulate/${scenario}`);

export const requestAccountChange = (body: AccountChangeIn) =>
  apiPost<AccountChange>("/supplier/accounts/change-request", body);
export const listAccountChanges = (signal?: AbortSignal) =>
  apiGet<{ items: AccountChange[] }>("/supplier/accounts/change-requests", opts(signal));

/** In-page signal so the nav badge and bell refetch right after a decision. */
export const APPROVALS_CHANGED = "setu:approvals-changed";
export const PHONE_OPEN = "setu:phone-open";
export const notifyApprovalsChanged = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(APPROVALS_CHANGED));
};
export const openDemoPhone = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(PHONE_OPEN));
};
