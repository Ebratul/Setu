import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { Day, Forecast } from "@/lib/api/cashflow";

import { CashflowCalendar } from "./CashflowCalendar";

const day = (on: string, below: boolean): Day => ({
  on,
  opening: "100.00",
  inflow: "0.00",
  outflow: "0.00",
  net: "0.00",
  closing: below ? "-50.00" : "100.00",
  below_buffer: below,
  items: [],
});

const forecast = {
  currency: "USD",
  weekly: [
    {
      start: "2026-11-06",
      end: "2026-11-07",
      inflow: "0.00",
      outflow: "0.00",
      closing: "0.00",
      lowest: "0.00",
    },
  ],
  daily: [day("2026-11-06", false), day("2026-11-07", true)],
} as unknown as Forecast;

function Harness() {
  const [sel, setSel] = useState<string | null>(null);
  return (
    <CashflowCalendar forecast={forecast} selected={sel} onSelect={setSel} />
  );
}

describe("CashflowCalendar", () => {
  it("selects a day and marks below-buffer days with text", () => {
    render(<Harness />);
    const low = screen.getByRole("button", { name: /Nov 7, 2026.*Below/ });
    expect(screen.getByText(/Low/)).toBeInTheDocument();
    expect(low).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(low);
    expect(low).toHaveAttribute("aria-pressed", "true");
  });
});
