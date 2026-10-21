"use client";

import { useState } from "react";

import { useT } from "@/i18n";
import { getAuthClient } from "@/lib/auth/client";
import { attempt } from "@/lib/auth/flow";

type Props = {
  next: string | null;
  onError: (key: string) => void;
  disabled?: boolean;
};

function GoogleMark() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 48 48"
      width="20"
      height="20"
    >
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

/** Where Google sends the browser back to; LoginScreen finishes the Setu session there. */
export function oauthCallbackUrl(origin: string, next: string | null): string {
  const q = new URLSearchParams({ oauth: "1" });
  if (next) q.set("next", next);
  return `${origin}/login?${q.toString()}`;
}

export function GoogleButton({ next, onError, disabled = false }: Props) {
  const t = useT();
  const [busy, setBusy] = useState(false);

  async function go() {
    setBusy(true);
    onError("");
    const res = await attempt<{ url?: string }>(() =>
      getAuthClient().signIn.social({
        provider: "google",
        callbackURL: oauthCallbackUrl(window.location.origin, next),
      }),
    );
    if (res.error) {
      onError("lg.googleFailed");
      setBusy(false);
      return;
    }
    if (res.data?.url) window.location.assign(res.data.url);
  }

  return (
    <button
      type="button"
      onClick={() => void go()}
      disabled={busy || disabled}
      aria-busy={busy || undefined}
      className="inline-flex min-h-12 w-full items-center justify-center gap-3 rounded-xl border border-muted bg-surface px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-60"
    >
      <GoogleMark />
      <span>{busy ? t("lg.googleBusy") : t("lg.google")}</span>
    </button>
  );
}
