import { clearAccessToken, getAccessToken, getAuthMode } from "@/lib/auth/client";

import type { components } from "./schema.gen";

export type HealthResponse = components["schemas"]["HealthResponse"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  /** Stable machine-readable reason from the problem JSON, e.g. EVIDENCE_NOT_VERIFIED. */
  readonly code: string | null;
  /** Seconds from the Retry-After header (429 only), else null. */
  readonly retryAfter: number | null;

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
  try {
    const body: unknown = await res.json();
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
  return new ApiError(
    res.status,
    `${method} ${path} failed with ${res.status}`,
    detail,
    code,
    Number.isFinite(ra) && ra > 0 ? ra : null,
  );
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
  if (!res.ok) throw await toError(method, path, res);
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
