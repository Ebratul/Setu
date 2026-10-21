import type { components } from "./schema.gen";
import { ApiError, apiGet, apiPost } from "./client";

type S = components["schemas"];

export type Bi = S["Bi"];
export type DemoScript = S["ScriptOut"];
export type DemoStep = S["StepDefOut"];
export type DemoScene = S["SceneDefOut"];
export type DemoScoreDef = S["ScoreDefOut"];
export type DemoTag = DemoStep["tag"];
export type Preflight = S["PreflightOut"];
export type PreflightItem = S["PreflightItem"];
export type DemoSandbox = S["SandboxOut"];
export type DemoRun = S["RunOut"];
export type SceneResult = S["SceneResultOut"];
export type ScoreItem = S["ScoreItemOut"];
export type DemoSummary = S["app__schemas__demo__SummaryOut"];
export type SkipResult = S["CoolingOffOut"];

const fresh = (signal?: AbortSignal): RequestInit => ({ signal, cache: "no-store" });

export const getDemoSteps = (signal?: AbortSignal) => apiGet<DemoScript>("/demo/steps", fresh(signal));
export const getPreflight = (signal?: AbortSignal) => apiGet<Preflight>("/demo/preflight", fresh(signal));
export const startSandbox = (fresh_ = false) => apiPost<DemoSandbox>("/demo/sandbox", { fresh: fresh_ });
export const getSandbox = (signal?: AbortSignal) => apiGet<DemoSandbox>("/demo/sandbox", fresh(signal));
export const endSandbox = () => apiDelete("/demo/sandbox");
export const setLiveAi = (enabled: boolean) => apiPost<DemoSandbox>("/demo/sandbox/live-ai", { enabled });
export const skipCoolingOff = () => apiPost<SkipResult>("/demo/sandbox/skip-cooling-off");
export const getRun = (signal?: AbortSignal) => apiGet<DemoRun>("/demo/run", fresh(signal));
export const runScene = (n: number, k: number, force = false) =>
  apiPost<DemoRun>(`/demo/run/scenes/${n}/${k}/run${force ? "?force=true" : ""}`);
export const gotoStep = (step: number) => apiPost<DemoRun>("/demo/run/goto", { step });
export const resetRun = () => apiPost<DemoRun>("/demo/run/reset");
export const getSummary = (signal?: AbortSignal) => apiGet<DemoSummary>("/demo/run/summary", fresh(signal));

async function apiDelete(path: string): Promise<void> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
  const res = await fetch(`${base}${path}`, { method: "DELETE", credentials: "same-origin" });
  if (!res.ok && res.status !== 204) throw new ApiError(res.status, `DELETE ${path} failed with ${res.status}`);
}

export type DemoErrorKind = "expired" | "rate" | "capacity" | "required" | "network" | "other";

/** Maps an API failure to a friendly category (never shows a stack trace). */
export function demoErrorKind(e: unknown): DemoErrorKind {
  if (e instanceof ApiError) {
    if (e.status === 410 || e.code === "SANDBOX_EXPIRED") return "expired";
    if (e.status === 429 || e.code === "SANDBOX_RATE_LIMIT") return "rate";
    if (e.status === 503 || e.code === "SANDBOX_CAPACITY") return "capacity";
    if (e.code === "SANDBOX_REQUIRED") return "required";
    return "other";
  }
  return "network";
}

/** Runs `fn`; on a 429 waits Retry-After (default 5 s, max 30 s) and retries once. */
export async function withRateRetry<T>(
  fn: () => Promise<T>,
  sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
  onWait?: (seconds: number) => void,
): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (demoErrorKind(e) !== "rate") throw e;
    const secs = Math.min(30, (e instanceof ApiError && e.retryAfter) || 5);
    onWait?.(secs);
    await sleep(secs * 1000);
    return fn();
  }
}
