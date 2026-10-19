import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type RiskOut = S["RiskOut"];
export type TraceItem = S["TraceItemOut"];
export type RiskHint = S["HintOut"];
export type DryRunRequest = S["DryRunRequest"];
export type DryRunOut = S["DryRunOut"];
export type PolicyOut = S["PolicyOut"];
export type PolicyRule = S["PolicyRule"];
export type RiskOverview = S["OverviewOut"];
export type RiskEvent = S["EventRow"];
export type RiskKind = TraceItem["kind"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const evaluateRisk = (body: Partial<DryRunRequest>, signal?: AbortSignal) =>
  apiPost<DryRunOut>("/risk/evaluate", body, { signal });

export const getRiskPolicy = (signal?: AbortSignal) =>
  apiGet<PolicyOut>("/risk/policy", opts(signal));

export const getRiskOverview = (signal?: AbortSignal) =>
  apiGet<RiskOverview>("/risk/overview", opts(signal));
