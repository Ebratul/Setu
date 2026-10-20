import { hasKey } from "@/i18n";

import { ApiError } from "./client";
import { dealErrorText } from "./dealErrors";

/** Field path (e.g. "bank_account.account_number") -> server message, from a FastAPI 422 body. */
export function fieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!(error instanceof ApiError) || error.status !== 422 || !error.detail) return out;
  try {
    const items: unknown = JSON.parse(error.detail);
    if (!Array.isArray(items)) return out;
    for (const it of items) {
      const o = it as { loc?: unknown; msg?: unknown };
      if (!Array.isArray(o.loc)) continue;
      const path = o.loc.filter((p) => p !== "body").join(".");
      if (path && !(path in out)) out[path] = typeof o.msg === "string" ? o.msg : "";
    }
  } catch {
    /* detail was a plain message */
  }
  return out;
}

/**
 * Friendly text for an API failure: `<prefix>.<CODE>` first (screen-specific wording),
 * then the shared deal/API messages (which cover 403 codes such as VIEWER_READ_ONLY).
 */
export function apiErrorText(error: unknown, t: (key: string) => string, prefix: string): string {
  if (error instanceof ApiError && error.code && hasKey(`${prefix}.${error.code}`)) {
    return t(`${prefix}.${error.code}`);
  }
  return dealErrorText(error, t);
}
