import { ApiError } from "@/lib/api/client";
import { logout, startSession, type AppUser } from "@/lib/api/auth";
import { endAuthSession } from "@/lib/auth/client";

export function safeNext(next: string | null, role: string) {
  if (role === "SUPPLIER") {
    return next && /^\/supplier(\/|$)/.test(next) ? next : "/supplier";
  }
  return next && /^\/app(\/|$)/.test(next) ? next : "/app";
}

/** Landing path for a signed-in user: onboarding steps first, then the role's home. */
export function pathForUser(user: AppUser, next: string | null): string {
  switch (user.account_status) {
    case "PENDING_PROFILE":
      return statusPath("not_onboarded");
    case "PENDING_VERIFICATION":
      return statusPath("pending");
    case "REJECTED":
      return statusPath("rejected");
    case "SUSPENDED":
      return statusPath("suspended");
    default:
      return safeNext(next, user.role);
  }
}

/** Opens the Setu session after a Neon sign-in and returns where the user belongs. */
export async function finishSignIn(next: string | null): Promise<string> {
  return pathForUser(await startSession(), next);
}

export type StatusReason =
  "not_onboarded" | "pending" | "suspended" | "rejected";

/** Where a signed-in user with a non-active account belongs. */
export function statusPath(reason: StatusReason): string {
  if (reason === "not_onboarded") return "/onboarding";
  if (reason === "pending") return "/onboarding/status";
  return `/account-status?reason=${reason}`;
}

export type SignedInResult =
  { kind: "go"; path: string } | { kind: "error"; key: string };

/** Finishes a sign-in done elsewhere (Google redirect): opens the Setu session, retrying once for a late token. */
export async function resolveSignedIn(
  next: string | null,
): Promise<SignedInResult> {
  for (let attemptNo = 0; attemptNo < 2; attemptNo++) {
    try {
      return { kind: "go", path: await finishSignIn(next) };
    } catch (e) {
      const problem = classifyApiError(e);
      if (problem.kind === "status")
        return { kind: "go", path: statusPath(problem.reason) };
      if (problem.kind === "unverified")
        return { kind: "error", key: "auth.err.unverified" };
      if (attemptNo === 0 && e instanceof ApiError && e.status === 401) {
        await new Promise((r) => setTimeout(r, 700));
        continue;
      }
      return { kind: "error", key: problem.key };
    }
  }
  return { kind: "error", key: "auth.err.generic" };
}

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
      case "ACCOUNT_REJECTED":
        return { kind: "status", reason: "rejected" };
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
