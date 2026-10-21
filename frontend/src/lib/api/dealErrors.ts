import { hasKey } from "@/i18n";

import { ApiError } from "./client";

/** i18n key for an API failure: a stable problem `code` first, then the HTTP status, then generic. */
export function dealErrorKey(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code && hasKey(`dealErr.${error.code}`)) {
      return `dealErr.${error.code}`;
    }
    if (error.status === 403) return "dealErr.FORBIDDEN";
    if (error.status === 404) return "dealErr.NOT_FOUND";
    if (error.status === 422) return "dealErr.VALIDATION";
  }
  return "dealErr.generic";
}

/** Friendly localized text for an error; a server detail is appended only when the code is unknown. */
export function dealErrorText(
  error: unknown,
  t: (key: string) => string,
): string {
  const key = dealErrorKey(error);
  const base = t(key);
  if (
    key === "dealErr.generic" &&
    error instanceof ApiError &&
    error.detail &&
    error.status < 500
  ) {
    return `${base} (${error.detail})`;
  }
  return base;
}
