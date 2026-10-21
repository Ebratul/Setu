"use client";

import { Badge } from "@/components/ui/Badge";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { BuyerScopeGate } from "./BuyerScopeGate";
import { CashflowView } from "./CashflowView";

export function CashflowPage() {
  const t = useT();
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-ink">{t("cf.title")}</h1>
        <SimulatedBadge />
        <Badge>{t("common.simulatedData")}</Badge>
      </div>
      <BuyerScopeGate>
        {(partyId) => <CashflowView partyId={partyId} />}
      </BuyerScopeGate>
    </div>
  );
}
