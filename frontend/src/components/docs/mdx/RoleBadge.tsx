"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useT } from "@/i18n";

const ROLES: Record<string, { tone: Tone; icon: IconName }> = {
  buyer: { tone: "info", icon: "box" },
  supplier: { tone: "success", icon: "users" },
  admin: { tone: "warning", icon: "gear" },
  judge: { tone: "neutral", icon: "scale" },
};

export function RoleBadge({ role }: { role: string }) {
  const t = useT();
  const r = ROLES[role] ?? ROLES.buyer;
  return (
    <span className="mr-2 inline-flex">
      <Badge tone={r.tone} icon={<Icon name={r.icon} size={12} />}>
        {t(`docs.role.${role}`)}
      </Badge>
    </span>
  );
}
