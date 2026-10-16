"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { hasKey, useT } from "@/i18n";

const TONES: Record<string, Tone> = {
  DRAFT: "neutral",
  FUNDED: "info",
  COMPLETED: "success",
};

export function StatusBadge({ status }: { status: string }) {
  const t = useT();
  const key = `status.${status}`;
  return (
    <Badge tone={TONES[status] ?? "neutral"}>
      {hasKey(key) ? t(key) : status}
    </Badge>
  );
}
