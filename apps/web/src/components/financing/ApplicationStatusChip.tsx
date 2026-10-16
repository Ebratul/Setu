"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";
import type { Application } from "@/lib/api/financing";

type Props = { status: Application["status"] };

const TONE: Record<Application["status"], Tone> = {
  SUBMITTED: "info",
  APPROVED: "success",
  REJECTED: "danger",
  CANCELLED: "neutral",
};
const ICON: Record<Application["status"], string> = {
  SUBMITTED: "●",
  APPROVED: "✓",
  REJECTED: "✕",
  CANCELLED: "–",
};

export function ApplicationStatusChip({ status }: Props) {
  const t = useT();
  return (
    <Badge tone={TONE[status]} icon={ICON[status]}>
      {t(`fin.status.${status}`)}
    </Badge>
  );
}
