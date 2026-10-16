import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type Gap = S["GapOut"];
export type Match = S["MatchOut"];
export type OptionQuote = S["OptionQuote"];
export type TopPick = S["TopPick"];
export type Check = S["CheckOut"];
export type Schedule = S["ScheduleOut"];
export type Instalment = S["InstalmentOut"];
export type Impact = S["ImpactOut"];
export type Application = S["ApplicationOut"];
export type ApplicationList = S["ApplicationList"];
export type Approval = S["ApprovalOut"];
export type FinMode = Gap["mode"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

function query(params: Record<string, string | number | undefined>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") p.set(k, String(v));
  }
  const q = p.toString();
  return q ? `?${q}` : "";
}

export const getGap = (
  mode: FinMode,
  dealId?: string,
  partyId?: string,
  signal?: AbortSignal,
) =>
  apiGet<Gap>(
    `/financing/gap${query({ mode, deal_id: dealId, party_id: partyId })}`,
    opts(signal),
  );

export const matchOptions = (
  body: { mode: FinMode; deal_id?: string; party_id?: string; amount?: string },
  signal?: AbortSignal,
) => apiPost<Match>("/financing/match", body, opts(signal));

export const getSchedule = (
  code: string,
  amount: string,
  start?: string,
  dealId?: string,
  partyId?: string,
  signal?: AbortSignal,
) =>
  apiGet<Schedule>(
    `/financing/options/${encodeURIComponent(code)}/schedule${query({
      amount,
      start,
      deal_id: dealId,
      party_id: partyId,
    })}`,
    opts(signal),
  );

export type FinancingRequest = {
  option_id: string;
  amount: string;
  mode: FinMode;
  deal_id?: string;
  party_id?: string;
};

export const getImpact = (body: FinancingRequest, signal?: AbortSignal) =>
  apiPost<Impact>("/financing/impact", body, opts(signal));

export const applyFinancing = (body: FinancingRequest & { deal_id: string }) =>
  apiPost<Application>("/financing/applications", body);

export const simulateApproval = (id: string) =>
  apiPost<Approval>(
    `/financing/applications/${encodeURIComponent(id)}/simulate-approval`,
  );

export const listApplications = (partyId?: string, signal?: AbortSignal) =>
  apiGet<ApplicationList>(
    `/financing/applications${query({ party_id: partyId })}`,
    opts(signal),
  );
