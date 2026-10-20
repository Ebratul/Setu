import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

export type DemoUser = components["schemas"]["DemoUserOut"];
export type DemoUsers = components["schemas"]["DemoUsers"];
export type AccountStatus =
  | "PENDING_PROFILE"
  | "PENDING_VERIFICATION"
  | "ACTIVE"
  | "REJECTED"
  | "SUSPENDED";
/** The signed-in user. `account_status` is absent only on older servers (treated as ACTIVE). */
export type AppUser = DemoUser & { account_status?: AccountStatus; mfa_enabled?: boolean };
export type AuthConfig = {
  mode: "demo" | "neon";
  demo_enabled?: boolean;
  google_enabled?: boolean;
};
export type StepupToken = {
  token: string;
  expires_in_seconds: number;
  header: "X-Stepup";
};

export const getDemoUsers = (signal?: AbortSignal) =>
  apiGet<DemoUsers>("/auth/demo-users", { signal, cache: "no-store" });
export const demoLogin = (email: string) =>
  apiPost<AppUser>("/auth/demo-login", { email });
export const getMe = (signal?: AbortSignal) =>
  apiGet<AppUser>("/auth/me", { signal, cache: "no-store" });
export const logout = () => apiPost<void>("/auth/logout");
export const getAuthConfig = (signal?: AbortSignal) =>
  apiGet<AuthConfig>("/auth/config", { signal, cache: "no-store" });
/** Neon mode: call once right after sign-in; returns the Setu user for role routing. */
export const startSession = () => apiPost<AppUser>("/auth/session");
export const startStepup = () =>
  apiPost<{ sent: true; expires_in_seconds: number; starts_left: number }>(
    "/auth/stepup/start",
  );
export const verifyStepup = (code: string) =>
  apiPost<StepupToken>("/auth/stepup/verify", { code });
/** Audit-only: tells the API the browser just revoked Neon sessions (never throws into the caller's flow). */
export const recordSessionRevoked = (scope: "one" | "others" | "all") =>
  apiPost<void>("/auth/session/revoked", { scope }).catch(() => undefined);
