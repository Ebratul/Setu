import type { components } from "./schema.gen";
import { ApiError, apiGet, apiPost } from "./client";

export type CreditRecord = components["schemas"]["CreditRecordOut"];
export type CreditRecordCheck = components["schemas"]["app__api__credit_records__VerifyOut"];

/** The signed record of a completed deal, or null while none exists (404). */
export async function getCreditRecord(dealRef: string, signal?: AbortSignal): Promise<CreditRecord | null> {
  try {
    return await apiGet<CreditRecord>(`/credit-records/${encodeURIComponent(dealRef)}`, { signal, cache: "no-store" });
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export const verifyCreditRecord = (payload: CreditRecord["payload"], signature: string) =>
  apiPost<CreditRecordCheck>("/credit-records/verify", { payload, signature });
