import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type DealDetail = S["DealDetail"];
export type DealList = S["DealList"];
export type DealListItem = S["DealListItem"];
export type DealStatus = S["DealStatus"];
export type Milestone = S["MilestoneOut"];
export type MilestoneStatus = Milestone["status"];
export type EvidenceStatus = Milestone["evidence_status"];
export type EvidenceItem = S["EvidenceItem"];
export type EscrowCardData = S["EscrowCard"];
export type LedgerOut = S["LedgerOut"];
export type LedgerRow = S["LedgerRow"];
export type ActivityOut = S["ActivityOut"];
export type ActivityRow = S["ActivityRow"];
export type ReleaseResult = S["ReleaseResult"];
export type ActionFlag = S["ActionFlag"];
export type CreateDealRequest = S["CreateDealRequest"];
export type ProposeRequest = S["ProposeRequest"];
export type DealCurrency = DealDetail["currency"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });
const enc = encodeURIComponent;

export const listDeals = (status?: DealStatus, signal?: AbortSignal) =>
  apiGet<DealList>(`/deals${status ? `?status=${enc(status)}` : ""}`, opts(signal));

export const getDeal = (id: string, signal?: AbortSignal) =>
  apiGet<DealDetail>(`/deals/${enc(id)}`, opts(signal));

export const createDeal = (body: CreateDealRequest) =>
  apiPost<DealDetail>("/deals", body);

export const proposeMilestones = (id: string, body: ProposeRequest) =>
  apiPost<DealDetail>(`/deals/${enc(id)}/milestones/propose`, body);

export const confirmMilestones = (id: string) =>
  apiPost<DealDetail>(`/deals/${enc(id)}/milestones/confirm`, {});

export const fundEscrow = (id: string, amount?: string) =>
  apiPost<DealDetail>(`/deals/${enc(id)}/escrow/fund`, {
    amount: amount ?? null,
  });

export const releaseMilestone = (id: string, idempotencyKey: string) =>
  apiPost<ReleaseResult>(`/milestones/${enc(id)}/release`, {
    idempotency_key: idempotencyKey,
  });

export const getLedger = (id: string, signal?: AbortSignal) =>
  apiGet<LedgerOut>(`/deals/${enc(id)}/ledger`, opts(signal));

export const getActivity = (id: string, signal?: AbortSignal) =>
  apiGet<ActivityOut>(`/deals/${enc(id)}/activity`, opts(signal));

export const setEvidence = (id: string, status: EvidenceStatus) =>
  apiPost<S["EvidenceResult"]>(`/milestones/${enc(id)}/evidence`, { status });

/** The dev evidence control shows only when this public flag was set at build time (never in production). */
export const DEV_TOOLS = process.env.NEXT_PUBLIC_DEV_TOOLS === "1";

export function newIdempotencyKey(milestoneId: string): string {
  const rnd =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : String(Date.now());
  return `rel-${milestoneId.slice(0, 8)}-${rnd}`;
}
