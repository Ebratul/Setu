import { hasKey } from "@/i18n";
import { ApiError } from "@/lib/api/client";

import type { Errors } from "./validate";

export const labelKey = (key: string) => key.replace(/\./g, "_");

/** Maps a 422 VALIDATION_FAILED `errors` list onto form fields; a known friendly code gets its own text. */
export function serverFieldErrors(error: unknown, known: readonly string[]): Errors {
  const out: Errors = {};
  if (!(error instanceof ApiError)) return out;
  for (const { field, code } of error.fields) {
    if (!known.includes(field) || field in out) continue;
    out[field] = { key: hasKey(`ob.srv.${code}`) ? `ob.srv.${code}` : "ob.v.server" };
  }
  return out;
}

export const isUnauthenticated = (e: unknown) =>
  e instanceof ApiError && e.status === 401;
