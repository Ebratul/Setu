"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";

type Props = { tier: number; decision?: string };

const TONES: Record<number, { tone: Tone; icon: string }> = {
  0: { tone: "neutral", icon: "○" },
  1: { tone: "info", icon: "ℹ" },
  2: { tone: "warning", icon: "▲" },
  3: { tone: "danger", icon: "⚠" },
};

export function TierBadge({ tier, decision }: Props) {
  const t = useT();
  const blocked = decision === "BLOCK";
  const m = blocked ? { tone: "danger" as Tone, icon: "⛔" } : (TONES[tier] ?? TONES[3]);
  return (
    <span data-testid="tier-badge" data-tier={blocked ? "blocked" : tier}>
      <Badge tone={m.tone} icon={m.icon}>
        {blocked ? t("risk.tier.blocked") : t(`risk.tier.${Math.min(Math.max(tier, 0), 3)}`)}
      </Badge>
    </span>
  );
}
