import type { components } from "./schema.gen";
import { API_BASE_URL, apiGet, apiPost } from "./client";

type S = components["schemas"];
export type AuditEntry = S["EntryOut"];
export type AuditEntryDetail = S["EntryDetailOut"];
export type AuditEntries = S["EntriesOut"];
export type AuditVerify = S["app__api__audit__VerifyOut"];
export type AuditSummary = S["app__api__audit__SummaryOut"];
export type AuditPublicKey = S["PublicKeyOut"];
export type TamperIn = S["TamperIn"];
export type TamperOut = S["TamperOut"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const getAuditPublicKey = (signal?: AbortSignal) =>
  apiGet<AuditPublicKey>("/audit/public-key", opts(signal));

export const getAuditSummary = (signal?: AbortSignal) => apiGet<AuditSummary>("/audit/summary", opts(signal));

export function getAuditEntries(q: { after?: number; limit?: number; dealId?: string; action?: string }, signal?: AbortSignal) {
  const p = new URLSearchParams();
  if (q.after) p.set("after", String(q.after));
  p.set("limit", String(q.limit ?? 30));
  if (q.dealId) p.set("deal_id", q.dealId);
  if (q.action) p.set("action", q.action);
  return apiGet<AuditEntries>(`/audit/entries?${p}`, opts(signal));
}

export const getAuditEntry = (seq: number, signal?: AbortSignal) =>
  apiGet<AuditEntryDetail>(`/audit/entries/${seq}`, opts(signal));

export const verifyAuditNow = (signal?: AbortSignal) => apiGet<AuditVerify>("/audit/verify", opts(signal));

export const tamperDemo = (body: TamperIn, signal?: AbortSignal) =>
  apiPost<TamperOut>("/audit/tamper-demo", body, { signal });

/** Same-origin download URL; the session cookie authorises it. */
export const auditExportUrl = (dealId?: string) =>
  `${API_BASE_URL}/audit/export?format=jsonl${dealId ? `&deal_id=${encodeURIComponent(dealId)}` : ""}`;
