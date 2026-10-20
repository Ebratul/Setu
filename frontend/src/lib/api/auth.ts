import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

export type DemoUser = components["schemas"]["DemoUserOut"];
export type DemoUsers = components["schemas"]["DemoUsers"];

export const getDemoUsers = (signal?: AbortSignal) =>
  apiGet<DemoUsers>("/auth/demo-users", { signal, cache: "no-store" });
export const demoLogin = (email: string) =>
  apiPost<DemoUser>("/auth/demo-login", { email });
export const getMe = (signal?: AbortSignal) =>
  apiGet<DemoUser>("/auth/me", { signal, cache: "no-store" });
export const logout = () => apiPost<void>("/auth/logout");
