"use client";

import { useState } from "react";

type Props = { text: string; copyValue: string; ariaLabel: string; copiedLabel: string; testId?: string };

/** Small chip that copies `copyValue`; clipboard failures are ignored (the text stays selectable). */
export function CopyChip({ text, copyValue, ariaLabel, copiedLabel, testId }: Props) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(copyValue);
      setDone(true);
      setTimeout(() => setDone(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={ariaLabel}
      data-testid={testId}
      className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-alt px-2.5 py-0.5 font-mono text-xs font-semibold text-ink hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
    >
      <span aria-hidden="true">{done ? "✓" : "⧉"}</span>
      <span aria-live="polite">{done ? copiedLabel : text}</span>
    </button>
  );
}
