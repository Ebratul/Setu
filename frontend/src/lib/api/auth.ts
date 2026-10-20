import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

export type DemoUser = components["schemas"]["DemoUserOut"];
export type AuthConfig = components["schemas"]["AuthConfig"];
export type DemoUsers = components["schemas"]["DemoUsers"];

export const getDemoUsers = (signal?: AbortSignal) =>
  apiGet<DemoUsers>("/auth/demo-users", { signal, cache: "no-store" });
export const demoLogin = (email: string) =>
  apiPost<DemoUser>("/auth/demo-login", { email });
export const getMe = (signal?: AbortSignal) =>
  apiGet<DemoUser>("/auth/me", { signal, cache: "no-store" });
export const logout = () => apiPost<void>("/auth/logout");
export const getAuthConfig = (signal?: AbortSignal) =>
  apiGet<AuthConfig>("/auth/config", { signal, cache: "no-store" });
/** Neon mode: call once right after sign-in; returns the Setu user for role routing. */
export const startSession = () => apiPost<DemoUser>("/auth/session");
