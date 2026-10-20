"use client";

import { useState } from "react";

import { useT } from "@/i18n";
import { DEV_TOOLS, setEvidence, type Milestone } from "@/lib/api/deals";
import { ApiError } from "@/lib/api/client";

type Props = { milestone: Milestone; onDone: () => void };

/** Development-only: stands in for the document pipeline. Hidden unless NEXT_PUBLIC_DEV_TOOLS=1 and the endpoint exists. */
export function DevEvidenceControl({ milestone, onDone }: Props) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [gone, setGone] = useState(false);
  if (!DEV_TOOLS || gone) return null;
  if (milestone.evidence_status === "VERIFIED") return null;
  if (["RELEASED", "REFUNDED", "CANCELLED"].includes(milestone.status)) return null;

  async function mark() {
    setBusy(true);
    try {
      await setEvidence(milestone.id, "VERIFIED");
      onDone();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setGone(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      data-testid="dev-evidence"
      disabled={busy}
      onClick={mark}
      className="mt-2 rounded-lg border border-dashed border-muted px-2 py-1 text-xs text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none disabled:opacity-50"
    >
      {t("dev.markVerified")}
    </button>
  );
}
