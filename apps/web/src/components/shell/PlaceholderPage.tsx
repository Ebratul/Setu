"use client";

import { Card } from "@/components/ui/Card";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

type Props = { titleKey: string; bodyKey: string };

export function PlaceholderPage({ titleKey, bodyKey }: Props) {
  const t = useT();
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t(titleKey)}</h1>
        <SimulatedBadge />
      </div>
      <Card>
        <p className="text-muted">{t(bodyKey)}</p>
      </Card>
    </div>
  );
}
