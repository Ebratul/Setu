import { clearAccessToken, getAccessToken, getAuthMode } from "@/lib/auth/client";

import type { components } from "./schema.gen";

export type HealthResponse = components["schemas"]["HealthResponse"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

/** Fired on any 403 ACCOUNT_NOT_VERIFIED so the shell can explain it once, whatever screen made the call. */
export const NOT_VERIFIED_EVENT = "setu:account-not-verified";

/** Fired on 403 ACCOUNT_SUSPENDED / ACCOUNT_REJECTED / MFA_REQUIRED (outside /auth/) so the shell can route the user. */
export const ACCOUNT_BLOCK_EVENT = "setu:account-block";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  /** Stable machine-readable reason from the problem JSON, e.g. EVIDENCE_NOT_VERIFIED. */
  readonly code: string | null;
  /** Seconds from the Retry-After header (429 only), else null. */
  readonly retryAfter: number | null;
  /** Per-field problems from a 422 VALIDATION_FAILED body: `field` is the dotted request key. */
  fields: { field: string; code: string }[] = [];

  constructor(
    status: number,
    message: string,
    detail: string | null = null,
    code: string | null = null,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.retryAfter = retryAfter;
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

async function toError(method: string, path: string, res: Response) {
  let detail: string | null = null;
  let code: string | null = null;
  let fields: { field: string; code: string }[] = [];
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && Array.isArray((body as { errors?: unknown }).errors)) {
      fields = ((body as { errors: unknown[] }).errors)
        .map((e) => e as { field?: unknown; code?: unknown })
        .filter((e) => typeof e.field === "string" && typeof e.code === "string")
        .map((e) => ({ field: e.field as string, code: e.code as string }));
    }
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    }
    if (body && typeof body === "object" && "code" in body) {
      const c = (body as { code: unknown }).code;
      if (typeof c === "string") code = c;
    }
  } catch {
    /* non-JSON error body */
  }
  const ra = Number(res.headers.get("Retry-After"));
  const err = new ApiError(
    res.status,
    `${method} ${path} failed with ${res.status}`,
    detail,
    code,
    Number.isFinite(ra) && ra > 0 ? ra : null,
  );
  err.fields = fields;
  return err;
}

/** Bearer token in neon mode; null in demo mode (cookie auth) or when signed out. */
async function bearer(path: string, force: boolean): Promise<string | null> {
  if (path === "/auth/config") return null;
  try {
    if ((await getAuthMode()) !== "neon") return null;
  } catch {
    return null;
  }
  return getAccessToken({ force });
}

async function send(method: string, path: string, init: RequestInit | undefined, force: boolean) {
  const token = await bearer(path, force);
  const headers: Record<string, string> = { Accept: "application/json" };
  Object.assign(headers, init?.headers);
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...init,
    method,
    headers,
  });
}

async function request<T>(
  method: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  let res = await send(method, path, init, false);
  if (res.status === 401) {
    const err = await toError(method, path, res.clone());
    if (err.code === "TOKEN_INVALID" || err.code === "UNAUTHENTICATED") {
      // The access token may simply have expired: refresh once and retry.
      clearAccessToken();
      if ((await bearer(path, true)) !== null) res = await send(method, path, init, false);
    }
  }
  if (!res.ok) {
    const err = await toError(method, path, res);
    if (
      err.status === 403 &&
      err.code === "ACCOUNT_NOT_VERIFIED" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event(NOT_VERIFIED_EVENT));
    }
    if (
      err.status === 403 &&
      typeof window !== "undefined" &&
      !path.startsWith("/auth/") &&
      (err.code === "ACCOUNT_SUSPENDED" || err.code === "ACCOUNT_REJECTED" || err.code === "MFA_REQUIRED")
    ) {
      window.dispatchEvent(new CustomEvent(ACCOUNT_BLOCK_EVENT, { detail: err.code }));
    }
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>("GET", path, init);
}

export function apiPost<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  return request<T>("POST", path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function withJson(init: RequestInit | undefined, body: unknown): RequestInit {
  return {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export function apiPut<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  return request<T>("PUT", path, withJson(init, body));
}

export function apiPatch<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  return request<T>("PATCH", path, withJson(init, body));
}

/** Authenticated GET of a binary body (signed document links need the bearer header, so no plain <a href>). */
export async function apiBlob(path: string): Promise<Blob> {
  const res = await send("GET", path, undefined, false);
  if (!res.ok) throw await toError("GET", path, res);
  return res.blob();
}

export function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>("DELETE", path, init);
}

/** multipart/form-data POST; the browser sets the boundary header itself. */
export function apiPostForm<T>(
  path: string,
  body: FormData,
  init?: RequestInit,
): Promise<T> {
  return request<T>("POST", path, { ...init, body });
}

export const API_BASE_URL = API_BASE;

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health", { signal, cache: "no-store" });
}
