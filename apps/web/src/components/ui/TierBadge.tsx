"use client";

import { useT } from "@/i18n";

import { Badge, type Tone } from "./Badge";
import { Icon, type IconName } from "./Icon";

type Props = { tier: number; decision?: string };

const TONES: Record<number, { tone: Tone; icon: IconName }> = {
  0: { tone: "neutral", icon: "circle" },
  1: { tone: "info", icon: "info" },
  2: { tone: "warning", icon: "warn" },
  3: { tone: "danger", icon: "lock" },
};

/** Tier 0 neutral, 1 info, 2 warning, 3 danger, BLOCK danger; always icon + text. */
export function TierBadge({ tier, decision }: Props) {
  const t = useT();
  const blocked = decision === "BLOCK";
  const m = blocked ? { tone: "danger" as Tone, icon: "ban" as IconName } : (TONES[tier] ?? TONES[3]);
  return (
    <span data-testid="tier-badge" data-tier={blocked ? "blocked" : tier}>
      <Badge tone={m.tone} icon={<Icon name={m.icon} size={12} />}>
        {blocked ? t("risk.tier.blocked") : t(`risk.tier.${Math.min(Math.max(tier, 0), 3)}`)}
      </Badge>
    </span>
  );
}
