import type { components } from "./schema.gen";

export type HealthResponse = components["schemas"]["HealthResponse"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  /** Stable machine-readable reason from the problem JSON, e.g. EVIDENCE_NOT_VERIFIED. */
  readonly code: string | null;

  constructor(
    status: number,
    message: string,
    detail: string | null = null,
    code: string | null = null,
  ) {
    super(message);
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
  return new ApiError(
    res.status,
    `${method} ${path} failed with ${res.status}`,
    detail,
    code,
  );
}

async function request<T>(
  method: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...init,
    method,
    headers: { Accept: "application/json", ...init?.headers },
  });
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
