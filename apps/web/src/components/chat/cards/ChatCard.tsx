"use client";

import type { ChatCardData } from "@/lib/api/chat";

import { AlertsCard } from "./AlertsCard";
import { CashflowCard } from "./CashflowCard";
import { FinancingComparisonCard } from "./FinancingComparisonCard";
import { FxCompareCard } from "./FxCompareCard";
import { KybCard } from "./KybCard";
import { LandedCostCard } from "./LandedCostCard";
import { MonthlySummaryCard } from "./MonthlySummaryCard";
import { ScorecardCard } from "./ScorecardCard";

/** Dispatches on the discriminated `card_type`; unknown types render nothing. */
export function ChatCard({ card }: { card: ChatCardData }) {
  switch (card.card_type) {
    case "landed_cost":
      return <LandedCostCard card={card} />;
    case "cashflow":
      return <CashflowCard card={card} />;
    case "alerts":
      return <AlertsCard card={card} />;
    case "financing_comparison":
      return <FinancingComparisonCard card={card} />;
    case "fx_compare":
      return <FxCompareCard card={card} />;
    case "monthly_summary":
      return <MonthlySummaryCard card={card} />;
    case "scorecard":
      return <ScorecardCard card={card} />;
    case "kyb":
      return <KybCard card={card} />;
    default:
      return null;
  }
}
