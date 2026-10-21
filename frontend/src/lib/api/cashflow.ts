import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type Forecast = S["ForecastOut"];
export type Day = S["DayOut"];
export type Flow = S["FlowOut"];
export type Week = S["WeekOut"];
export type ScenarioRequest = S["ScenarioRequest"];
export type ScenarioOut = S["ScenarioOut"];
export type AlertPreview = S["AlertPreview"];
export type Alert = S["AlertOut"];
export type AlertAction = S["AlertAction"];
export type AlertList = S["AlertList"];
export type AlertStatus = Alert["status"];
export type AlertType = Alert["type"];
export type Severity = Alert["severity"];
export type Recompute = S["RecomputeOut"];
export type Dashboard = S["DashboardOut"];
export type DashboardDeal = S["DashboardDeal"];

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

function query(params: Record<string, string | number | undefined>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") p.set(k, String(v));
  }
  const q = p.toString();
  return q ? `?${q}` : "";
}

export const getForecast = (
  partyId?: string,
  days = 90,
  minBuffer?: string,
  signal?: AbortSignal,
) =>
  apiGet<Forecast>(
    `/cashflow/forecast${query({ party_id: partyId, days, min_buffer: minBuffer })}`,
    opts(signal),
  );

export const runScenario = (body: ScenarioRequest, signal?: AbortSignal) =>
  apiPost<ScenarioOut>("/cashflow/scenario", body, opts(signal));

export const getAlerts = (
  partyId?: string,
  status?: AlertStatus,
  signal?: AbortSignal,
) =>
  apiGet<AlertList>(
    `/alerts${query({ party_id: partyId, status })}`,
    opts(signal),
  );

export const acknowledgeAlert = (id: string) =>
  apiPost<Alert>(`/alerts/${encodeURIComponent(id)}/acknowledge`);

export const resolveAlert = (id: string) =>
  apiPost<Alert>(`/alerts/${encodeURIComponent(id)}/resolve`);

export const recomputeAlerts = (partyId?: string) =>
  apiPost<Recompute>(`/alerts/recompute${query({ party_id: partyId })}`);

export const getDashboard = (partyId?: string, signal?: AbortSignal) =>
  apiGet<Dashboard>(`/dashboard${query({ party_id: partyId })}`, opts(signal));
