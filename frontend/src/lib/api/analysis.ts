import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type Amounts = S["Amounts"];
export type OrderAnalysis = S["OrderAnalysis"];
export type OrderList = S["OrderList"];
export type DealSummary = S["DealSummary"];
export type CostLineOut = S["CostLineOut"];
export type FxRate = S["FxRateOut"];
export type Explanation = S["Explanation"];
export type LandedCostRequest = S["LandedCostRequest"];
export type CostLineIn = S["CostLineIn"];
export type MonthlySummary = S["MonthlySummaryOut"];
export type MonthTotals = S["MonthTotalsOut"];
export type SupplierScorecard = S["SupplierScorecardOut"];
export type SupplierScore = S["SupplierScoreOut"];
export type Currency = keyof Amounts;

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const getOrders = (signal?: AbortSignal) =>
  apiGet<OrderList>("/analysis/orders", opts(signal));

export function getOrderAnalysis(
  ref: string,
  targetMarginPct?: string,
  signal?: AbortSignal,
) {
  const q = targetMarginPct
    ? `?target_margin_pct=${encodeURIComponent(targetMarginPct)}`
    : "";
  return apiGet<OrderAnalysis>(
    `/analysis/orders/${encodeURIComponent(ref)}${q}`,
    opts(signal),
  );
}

export const postLandedCost = (body: LandedCostRequest, signal?: AbortSignal) =>
  apiPost<OrderAnalysis>("/analysis/landed-cost", body, opts(signal));

export function getMonthly(
  month?: string,
  partyId?: string,
  signal?: AbortSignal,
) {
  const p = new URLSearchParams();
  if (month) p.set("month", month);
  if (partyId) p.set("party_id", partyId);
  const q = p.toString();
  return apiGet<MonthlySummary>(
    `/analysis/monthly${q ? `?${q}` : ""}`,
    opts(signal),
  );
}

export const getSuppliers = (signal?: AbortSignal) =>
  apiGet<SupplierScorecard>("/analysis/suppliers", opts(signal));
