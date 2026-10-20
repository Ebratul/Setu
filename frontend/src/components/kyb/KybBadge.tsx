"use client";

import { toneClasses, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";
import type { KybBadgeStatus } from "@/lib/api/kyb";

const META: Record<KybBadgeStatus, { tone: Tone; icon: string }> = {
  VERIFIED: { tone: "success", icon: "✓" },
  WARNING: { tone: "warning", icon: "▲" },
  BLOCKED: { tone: "danger", icon: "✕" },
  PENDING: { tone: "neutral", icon: "?" },
};

type Props = { status: KybBadgeStatus };

/** Status is conveyed by icon + text + colour, never colour alone. */
export function KybBadge({ status }: Props) {
  const t = useT();
  const meta = META[status] ?? META.PENDING;
  const label = t(`kyb.${status in META ? status : "PENDING"}`);
  return (
    <span
      data-testid="kyb-badge"
      data-status={status}
      aria-label={t("kyb.badgeLabel", { status: label })}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${toneClasses[meta.tone]}`}
    >
      <span aria-hidden="true">{meta.icon}</span>
      {label}
    </span>
  );
}
