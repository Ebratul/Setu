import type { components } from "./schema.gen";

export type HealthResponse = components["schemas"]["HealthResponse"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function toError(method: string, path: string, res: Response) {
  let detail: string | null = null;
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as { detail: unknown }).detail;
      detail = typeof d === "string" ? d : JSON.stringify(d);
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(
    res.status,
    `${method} ${path} failed with ${res.status}`,
    detail,
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

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health", { signal, cache: "no-store" });
}
