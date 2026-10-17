"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { hasKey, useT } from "@/i18n";

const TONES: Record<string, Tone> = {
  DRAFT: "neutral",
  PROPOSED: "info",
  CONFIRMED: "info",
  FUNDED: "info",
  IN_PRODUCTION: "info",
  SHIPPED: "info",
  ARRIVED: "info",
  COMPLETED: "success",
  DISPUTED: "danger",
  CANCELLED: "neutral",
};

const ICONS: Record<string, string> = {
  DRAFT: "✎",
  PROPOSED: "…",
  CONFIRMED: "✓",
  FUNDED: "●",
  IN_PRODUCTION: "⚙",
  SHIPPED: "→",
  ARRIVED: "⚑",
  COMPLETED: "✓",
  DISPUTED: "▲",
  CANCELLED: "✕",
};

export function StatusBadge({ status }: { status: string }) {
  const t = useT();
  const key = `status.${status}`;
  return (
    <Badge tone={TONES[status] ?? "neutral"} icon={ICONS[status]}>
      {hasKey(key) ? t(key) : status}
    </Badge>
  );
}
