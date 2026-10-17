import type { Tone } from "@/components/ui/Badge";
import type { EvidenceItem, MilestoneStatus } from "@/lib/api/deals";

/** Status is always shown as icon + text + tone, never colour alone. */
export const MILESTONE_META: Record<
  MilestoneStatus,
  { tone: Tone; icon: string; ring: string }
> = {
  PROPOSED: { tone: "neutral", icon: "✎", ring: "border-line" },
  PENDING: { tone: "neutral", icon: "◌", ring: "border-line" },
  READY: { tone: "info", icon: "●", ring: "border-info" },
  PENDING_APPROVAL: { tone: "warning", icon: "◔", ring: "border-warning" },
  RELEASED: { tone: "success", icon: "✓", ring: "border-success" },
  FROZEN: { tone: "danger", icon: "■", ring: "border-danger" },
  REFUNDED: { tone: "neutral", icon: "↩", ring: "border-line" },
  CANCELLED: { tone: "neutral", icon: "✕", ring: "border-line" },
};

export const EVIDENCE_META: Record<
  EvidenceItem["status"],
  { tone: Tone; icon: string }
> = {
  MISSING: { tone: "neutral", icon: "○" },
  PENDING: { tone: "warning", icon: "◔" },
  VERIFIED: { tone: "success", icon: "✓" },
  FLAGGED: { tone: "danger", icon: "▲" },
  REJECTED: { tone: "danger", icon: "✕" },
};

export const OPEN_STATUSES: MilestoneStatus[] = ["READY", "PENDING_APPROVAL"];
