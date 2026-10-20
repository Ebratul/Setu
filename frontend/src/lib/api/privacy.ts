import type {
  DryRunRequest,
  DryRunResult,
  PrivacyOverview,
  PrivacySummary,
  PrivacyXrayData,
} from "@/lib/privacy/types";

import { apiGet, apiPost } from "./client";

const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const privacyDryRun = (body: DryRunRequest, signal?: AbortSignal) =>
  apiPost<DryRunResult>("/privacy/dry-run", body, { signal });

export const getPrivacySummary = (threadId?: string | null, signal?: AbortSignal) =>
  apiGet<PrivacySummary>(
    threadId ? `/privacy/summary?thread_id=${encodeURIComponent(threadId)}` : "/privacy/summary",
    opts(signal),
  );

export const getPrivacyMessage = (id: string, signal?: AbortSignal) =>
  apiGet<PrivacyXrayData>(`/privacy/messages/${encodeURIComponent(id)}`, opts(signal));

export const getPrivacyDocument = (id: string, signal?: AbortSignal) =>
  apiGet<PrivacyXrayData>(`/privacy/documents/${encodeURIComponent(id)}`, opts(signal));

export const getPrivacyOverview = (signal?: AbortSignal) =>
  apiGet<PrivacyOverview>("/privacy/admin/overview", opts(signal));
