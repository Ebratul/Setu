"use client";

import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { BuyerScopeGate } from "./BuyerScopeGate";
import { DashboardView } from "./DashboardView";

export function DashboardPage() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("dash.title")}</h1>
        <SimulatedBadge />
      </div>
      <BuyerScopeGate>
        {(partyId) => <DashboardView partyId={partyId} />}
      </BuyerScopeGate>
    </div>
  );
}
