"use client";

import { useEffect } from "react";

import { useLang, useT } from "@/i18n";
import { loadDigits } from "@/lib/format";
import { useDigits } from "@/lib/useDigits";

/** Loads the stored digit style once, then shows a toggle only while Bangla is the active language. */
export function DigitsToggle() {
  const t = useT();
  const { lang } = useLang();
  const [digits, setDigits] = useDigits();
  useEffect(() => {
    loadDigits();
  }, []);
  if (lang !== "bn") return null;
  const native = digits === "native";
  return (
    <button
      type="button"
      data-testid="digits-toggle"
      aria-pressed={native}
      aria-label={t("digits.label") + ": " + t(native ? "digits.bangla" : "digits.latin")}
      title={t(native ? "digits.useLatin" : "digits.useBangla")}
      onClick={() => setDigits(native ? "latin" : "native")}
      className="flex size-11 items-center justify-center rounded-xl border border-line text-sm font-bold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <span aria-hidden="true">{native ? "১২৩" : "123"}</span>
    </button>
  );
}
