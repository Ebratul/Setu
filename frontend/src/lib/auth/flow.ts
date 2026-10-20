import { ApiError } from "@/lib/api/client";
import { logout, startSession } from "@/lib/api/auth";
import { endAuthSession } from "@/lib/auth/client";

export function safeNext(next: string | null, role: string) {
  if (role === "SUPPLIER") {
    return next && /^\/supplier(\/|$)/.test(next) ? next : "/supplier";
  }
  return next && /^\/app(\/|$)/.test(next) ? next : "/app";
}

/** Opens the Setu session after a Neon sign-in and returns the landing path for the user's role. */
export async function finishSignIn(next: string | null): Promise<string> {
  const user = await startSession();
  return safeNext(next, user.role);
}

export type StatusReason = "not_onboarded" | "pending" | "suspended";

export type SignInProblem =
  | { kind: "unverified" }
  | { kind: "status"; reason: StatusReason }
  | { kind: "message"; key: string };

export function classifyApiError(e: unknown): SignInProblem {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "EMAIL_NOT_VERIFIED":
        return { kind: "unverified" };
      case "ACCOUNT_NOT_ONBOARDED":
        return { kind: "status", reason: "not_onboarded" };
      case "ACCOUNT_PENDING":
        return { kind: "status", reason: "pending" };
      case "ACCOUNT_SUSPENDED":
        return { kind: "status", reason: "suspended" };
      case "UNAUTHENTICATED":
      case "TOKEN_INVALID":
        return { kind: "message", key: "auth.err.session" };
    }
    if (e.status === 429) return { kind: "message", key: "auth.err.tooMany" };
  }
  return { kind: "message", key: "auth.err.generic" };
}

export type AuthFail = { code: string | null; status: number | null; message: string };
export type AuthResult<T> = { data: T | null; error: AuthFail | null };

function toFail(e: unknown): AuthFail {
  const o = (e && typeof e === "object" ? e : {}) as Record<string, unknown>;
  return {
    code: typeof o.code === "string" ? o.code : null,
    status: typeof o.status === "number" ? o.status : null,
    message: typeof o.message === "string" ? o.message : "",
  };
}

/** The Neon SDK may either return `{error}` or throw a normalized AuthApiError; callers get one shape. */
export async function attempt<T>(fn: () => Promise<{ data?: T | null; error?: unknown } | undefined>): Promise<AuthResult<T>> {
  try {
    const res = await fn();
    return res?.error ? { data: null, error: toFail(res.error) } : { data: (res?.data ?? null) as T | null, error: null };
  } catch (e) {
    return { data: null, error: toFail(e) };
  }
}

export function isUnverified(err: AuthFail | null): boolean {
  return err?.code === "email_not_confirmed" || err?.code === "EMAIL_NOT_VERIFIED";
}

/**
 * Maps a Neon Auth failure to an i18n key. The SDK normalizes Better Auth codes to snake_case
 * (INVALID_EMAIL_OR_PASSWORD -> invalid_credentials) and leaves plugin codes (OTP) as plain 4xx.
 */
export function authErrorKey(err: AuthFail | null | undefined, ctx: "default" | "otp" | "reset" = "default"): string {
  const code = (err?.code ?? "").toLowerCase();
  if (err?.status === 429 || code.startsWith("over_") || code === "too_many_attempts") return "auth.err.tooMany";
  if (ctx === "otp" && ["validation_failed", "feature_not_supported", "invalid_otp", "otp_expired", "bad_jwt", ""].includes(code)) {
    if (err?.status !== 500) return "auth.err.otp";
  }
  if (ctx === "reset" && ["bad_jwt", "validation_failed", "invalid_token", "feature_not_supported"].includes(code)) return "auth.err.resetToken";
  switch (code) {
    case "invalid_credentials":
    case "invalid_email_or_password":
    case "invalid_password":
    case "user_not_found":
      return "auth.err.invalid";
    case "email_not_confirmed":
    case "email_not_verified":
      return "auth.err.unverified";
    case "user_already_exists":
    case "email_exists":
      return "auth.err.exists";
    case "weak_password":
    case "password_too_short":
    case "password_too_long":
      return "auth.err.passwordLength";
  }
  return "auth.err.generic";
}

/** Best effort: records the logout in the audit log, then ends the Neon session. Never throws. */
export async function signOutEverywhere(): Promise<void> {
  try {
    await logout();
  } catch {
    /* the audit call is best effort */
  }
  try {
    await endAuthSession();
  } catch {
    /* session may already be gone */
  }
}
