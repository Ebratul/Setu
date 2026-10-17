import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type RegistryEntry = S["RegistryEntryOut"];
export type RegistryList = S["RegistryList"];
export type RegistryStats = S["RegistryStatsOut"];
export type DocumentRegistry = S["DocumentRegistryOut"];
export type LenderCheck = S["LenderCheckOut"];
export type RegistryPurpose = S["RegistryPurpose"];
export type RegistryStatus = S["RegistryStatus"];
export type RegistryResult = DocumentRegistry["result"];
export type RegistryState = DocumentRegistry["state"];
export type RegistryBlock = NonNullable<S["OptionQuote"]["registry_block"]>;

/** Party code the demo helper checks against ("Lender B"). */
export const LENDER_B_ID = "setu-partner-finance";

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export type RegistryFilters = {
  status?: RegistryStatus;
  result?: "EXACT_DUPLICATE" | "NEAR_DUPLICATE";
  purpose?: RegistryPurpose;
  limit?: number;
  offset?: number;
};

export function listRegistry(f: RegistryFilters, signal?: AbortSignal) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v !== undefined) p.set(k, String(v));
  const q = p.toString();
  return apiGet<RegistryList>(`/registry${q ? `?${q}` : ""}`, opts(signal));
}

export const getRegistryStats = (signal?: AbortSignal) =>
  apiGet<RegistryStats>("/registry/stats", opts(signal));

export const getDocumentRegistry = (id: string, signal?: AbortSignal) =>
  apiGet<DocumentRegistry>(`/documents/${encodeURIComponent(id)}/registry`, opts(signal));

export const lenderCheck = (lenderId: string, documentId: string) =>
  apiPost<LenderCheck>("/registry/lender-check", { lender_id: lenderId, document_id: documentId });

export const isDuplicate = (r: string) => r === "EXACT_DUPLICATE" || r === "NEAR_DUPLICATE";

/** Demo/judge mode: judge or admin sessions, or the public build flag. */
export function isDemoMode(role: string | null | undefined): boolean {
  return role === "JUDGE" || role === "ADMIN" || process.env.NEXT_PUBLIC_DEMO_MODE === "1";
}
