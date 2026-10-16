"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";
import type { Severity } from "@/lib/api/cashflow";

const TONE: Record<Severity, Tone> = {
  CRITICAL: "danger",
  WARNING: "warning",
  INFO: "info",
};
const ICON: Record<Severity, string> = {
  CRITICAL: "✖",
  WARNING: "▲",
  INFO: "ℹ",
};

type Props = { severity: Severity };

export function SeverityBadge({ severity }: Props) {
  const t = useT();
  return (
    <Badge tone={TONE[severity]} icon={ICON[severity]}>
      {t(`severity.${severity}`)}
    </Badge>
  );
}
