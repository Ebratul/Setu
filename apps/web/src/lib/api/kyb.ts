import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type KybResult = S["KybResult"];
export type KybCheck = S["KybCheckOut"];
export type KybStatus = KybResult["status"];
export type KybBadgeStatus = KybStatus | "PENDING";
export type SupplierList = S["SupplierList"];
export type SupplierListItem = S["SupplierListItem"];
export type SupplierProfile = S["SupplierProfile"];
export type AccountSummary = S["AccountSummary"];
export type PendingAccountResult = S["PendingAccountResult"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const getSuppliers = (signal?: AbortSignal) =>
  apiGet<SupplierList>("/suppliers", opts(signal));

export const getSupplier = (id: string, signal?: AbortSignal) =>
  apiGet<SupplierProfile>(`/suppliers/${encodeURIComponent(id)}`, opts(signal));

export const verifySupplier = (id: string, dealId?: string) =>
  apiPost<KybResult>(
    `/kyb/verify/${encodeURIComponent(id)}${
      dealId ? `?deal_id=${encodeURIComponent(dealId)}` : ""
    }`,
  );
