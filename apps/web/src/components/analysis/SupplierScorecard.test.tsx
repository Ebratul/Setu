import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SupplierScore } from "@/lib/api/analysis";

import { SupplierScorecard } from "./SupplierScorecard";

const base: SupplierScore = {
  supplier_id: "1",
  code: "A",
  name: "Good Co",
  city: "Ningbo",
  country: "CN",
  kyb_status: "VERIFIED",
  score: "90.00",
  score_trend: [],
  on_time_rate_pct: "98.00",
  dispute_rate_pct: "1.00",
  defect_rate_pct: "0.50",
  doc_mismatch_count: 0,
  deals_count: 3,
  completed_deals_count: 3,
  your_deals_count: 2,
  price_index: "1.00",
  flags: [],
  weak: false,
  notes: [],
};
const weak: SupplierScore = {
  ...base,
  supplier_id: "2",
  name: "Huameng Trading",
  kyb_status: "WARNING",
  score: "57.79",
  weak: true,
  flags: ["LOW_SCORE"],
  notes: [{ code: "FLAG_LOW_SCORE", en: "Score is low", bn: "স্কোর কম" }],
};

vi.mock("@/lib/api/analysis", () => ({
  getSuppliers: vi.fn(async () => ({
    simulated: true,
    party_id: null,
    window_months: 6,
    suppliers: [base, weak],
    facts: [],
  })),
}));

beforeEach(() => vi.clearAllMocks());

describe("SupplierScorecard", () => {
  it("flags weak suppliers and sorts via header buttons", async () => {
    render(<SupplierScorecard />);
    const weakCell = await screen.findByText("Huameng Trading");
    const row = weakCell.closest("tr") as HTMLElement;
    expect(row).toHaveAttribute("data-weak", "true");
    expect(within(row).getByText("Weak supplier")).toBeInTheDocument();
    expect(within(row).getByText("Score is low")).toBeInTheDocument();
    expect(within(row).getByText("Warning")).toBeInTheDocument();

    const header = screen.getByRole("columnheader", { name: /Supplier/ });
    expect(header).toHaveAttribute("aria-sort", "none");
    fireEvent.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(within(header).getByRole("button"));
    expect(header).toHaveAttribute("aria-sort", "descending");
  });
});
