import { apiGet, apiPatch, apiPost } from "./client";
import type { Lang } from "./onboarding";

export type AccountOut = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  language: Lang;
  account_status: string;
  auth_provider: string | null;
  mfa_enabled: boolean;
  terms_version: string | null;
  terms_accepted_at: string | null;
  party_name: string | null;
  mobile_masked: string | null;
  created_at: string;
  last_login_at: string | null;
};
export type TotpSetup = { otpauth_uri: string; secret: string };
export type RecoveryCodes = { recovery_codes: string[]; mfa_enabled: true };

const fresh = (signal?: AbortSignal) => ({
  signal,
  cache: "no-store" as const,
});

export const getAccount = (signal?: AbortSignal) =>
  apiGet<AccountOut>("/account", fresh(signal));
export const patchAccount = (body: { language?: Lang; full_name?: string }) =>
  apiPatch<AccountOut>("/account", body);
export const exportAccount = () => apiGet<unknown>("/account/export", fresh());
export const requestDeletion = () => apiPost<void>("/account/delete-request");

export const totpSetup = () => apiPost<TotpSetup>("/auth/mfa/totp/setup");
export const totpEnable = (code: string) =>
  apiPost<RecoveryCodes>("/auth/mfa/totp/enable", { code });
export const totpDisable = (code: string) =>
  apiPost<void>("/auth/mfa/totp/disable", { code });
export const totpRegenerate = (code: string) =>
  apiPost<RecoveryCodes>("/auth/mfa/totp/recovery-codes/regenerate", { code });
