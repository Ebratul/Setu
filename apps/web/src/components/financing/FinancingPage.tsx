"use client";

import { useSearchParams } from "next/navigation";

import { BuyerScopeGate } from "@/components/cashflow/BuyerScopeGate";

import { parseFinParams } from "./finParams";
import { FinancingWorkspace } from "./FinancingWorkspace";

export function FinancingPage() {
  const params = useSearchParams();
  const initial = parseFinParams(params);
  return (
    <BuyerScopeGate>
      {(partyId) => <FinancingWorkspace partyId={partyId} initial={initial} />}
    </BuyerScopeGate>
  );
}
