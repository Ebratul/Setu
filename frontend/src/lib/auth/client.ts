import { createAuthClient } from "@neondatabase/auth";
import { BetterAuthReactAdapter } from "@neondatabase/auth/react/adapters";

export type AuthMode = "demo" | "neon";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
/** Same-origin proxy to Neon Auth (src/app/neon-auth); keeps the session cookie first-party. */
export const AUTH_PROXY_PATH = "/neon-auth";
const REFRESH_MARGIN_MS = 60_000;

type NeonClient = ReturnType<typeof buildClient>;

function buildClient() {
  return createAuthClient(`${window.location.origin}${AUTH_PROXY_PATH}`, {
    adapter: BetterAuthReactAdapter(),
  });
}

let client: NeonClient | null = null;

/** Browser-only, created lazily. */
export function getAuthClient(): NeonClient {
  if (typeof window === "undefined") throw new Error("auth client is browser-only");
  client ??= buildClient();
  return client;
}

let modePromise: Promise<AuthMode> | null = null;

/** Which sign-in the backend runs. Cached for the page lifetime; a failed lookup is retried. */
export function getAuthMode(): Promise<AuthMode> {
  modePromise ??= fetch(`${API_BASE}/auth/config`, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    cache: "no-store",
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`auth config failed with ${res.status}`);
      const body = (await res.json()) as { mode?: string };
      return body.mode === "neon" ? "neon" : "demo";
    })
    .catch((e: unknown) => {
      modePromise = null;
      throw e;
    });
  return modePromise;
}

type CachedToken = { token: string; expMs: number };
let cached: CachedToken | null = null;
let inflight: Promise<string | null> | null = null;

function readExpMs(jwt: string): number {
  try {
    const part = jwt.split(".")[1] ?? "";
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    if (typeof exp === "number") return exp * 1000;
  } catch {
    /* unreadable payload: treat as already stale */
  }
  return 0;
}

function fresh(c: CachedToken | null): c is CachedToken {
  return c !== null && c.expMs - REFRESH_MARGIN_MS > Date.now();
}

async function fetchToken(): Promise<string | null> {
  let token: string | null = null;
  try {
    token = (await getAuthClient().token()).data?.token ?? null;
  } catch {
    /* not signed in: the SDK throws a 401 */
  }
  if (!token) return null;
  cached = { token, expMs: readExpMs(token) };
  return token;
}

/** Bearer JWT for the API; reused until ~60 s before expiry, concurrent refreshes share one request. */
export function getAccessToken(opts: { force?: boolean } = {}): Promise<string | null> {
  if (!opts.force && fresh(cached)) return Promise.resolve(cached.token);
  inflight ??= fetchToken().finally(() => {
    inflight = null;
  });
  return inflight;
}

export function clearAccessToken(): void {
  cached = null;
  inflight = null;
}

/** Ends the Neon session and forgets the token. Callers record the logout with the API first. */
export async function endAuthSession(): Promise<void> {
  try {
    await getAuthClient().signOut();
  } finally {
    clearAccessToken();
  }
}

/** Test helper: resets module state. */
export function resetAuthStateForTests(): void {
  client = null;
  modePromise = null;
  clearAccessToken();
}
