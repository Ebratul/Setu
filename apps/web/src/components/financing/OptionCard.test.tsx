import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { OptionQuote, TopPick } from "@/lib/api/financing";

import { OptionCard } from "./OptionCard";

const amt = (n: string) => ({ USD: n, BDT: n, CNY: n });

function option(over: Partial<OptionQuote>): OptionQuote {
  return {
    option_id: "id",
    code: "supplier-credit",
    name: "Supplier credit",
    kind: "SUPPLIER_CREDIT",
    provider_name: "Huaxin",
    rank: 1,
    recommended: false,
    eligible: true,
    tenor_days: 30,
    start_on: "2026-11-07",
    maturity_on: "2026-12-07",
    principal: amt("1560.00"),
    cost: {
      interest: amt("0.00"),
      fees: amt("0.00"),
      uplift: amt("31.20"),
      flat: amt("0.00"),
      total: amt("31.20"),
      per_30_days: amt("31.20"),
      effective_annual_rate_pct: "24.33",
    },
    collateral: "None",
    conditions: "Priced 2% higher",
    condition_count: 1,
    checks: [],
    why_not: [],
    risk_notes: [],
    facts: [],
    ...over,
  } as OptionQuote;
}

const pick = {
  option_id: "id",
  code: "supplier-credit",
  total_cost: amt("31.20"),
  saving_vs_next: amt("19.19"),
  key_conditions: [],
  why_codes: ["LOWEST_COST"],
  sentences: [{ code: "LOWEST_COST", en: "Lowest total cost.", bn: "কম খরচ।" }],
} as TopPick;

const noop = vi.fn();
const handlers = { onSchedule: noop, onImpact: noop, onApply: noop };

describe("OptionCard", () => {
  it("highlights the recommended option with badge, sentences and saving", () => {
    render(
      <OptionCard
        option={option({ recommended: true })}
        pick={pick}
        currency="USD"
        {...handlers}
      />,
    );
    const card = screen.getByTestId("option-card");
    expect(card).toHaveAttribute("data-recommended", "true");
    expect(within(card).getByText("Recommended")).toBeInTheDocument();
    expect(within(card).getByText("Lowest total cost.")).toBeInTheDocument();
    expect(within(card).getByText(/saves \$19\.19/i)).toBeInTheDocument();
    expect(
      within(card).getByRole("button", { name: /Apply/ }),
    ).toBeInTheDocument();
  });

  it("greys an ineligible option, lists why not and offers no Apply", () => {
    render(
      <OptionCard
        option={option({
          eligible: false,
          why_not: [
            {
              code: "MIN_AMOUNT",
              ok: false,
              en: "Below the USD 2,000 minimum.",
              bn: "ন্যূনতম সীমার নিচে।",
              params: {},
            },
          ],
        })}
        pick={null}
        currency="USD"
        {...handlers}
      />,
    );
    const card = screen.getByTestId("option-card");
    expect(card).toHaveAttribute("data-eligible", "false");
    expect(within(card).getByText("Not eligible")).toBeInTheDocument();
    expect(
      within(card).getByText("Below the USD 2,000 minimum."),
    ).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /Apply/ })).toBeNull();
    expect(within(card).queryByText("Recommended")).toBeNull();
  });
});
