import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AlertView } from "./AlertItem";
import { AlertPanel } from "./AlertPanel";

function alert(over: Partial<AlertView> & Pick<AlertView, "key">): AlertView {
  return {
    type: "INFO",
    severity: "INFO",
    title_en: over.key,
    title_bn: over.key,
    message_en: "msg",
    message_bn: "msg",
    amount: null,
    currency: null,
    due_on: null,
    deal_ref: null,
    milestone_seq: null,
    action: null,
    facts: {},
    ...over,
  };
}

describe("AlertPanel", () => {
  it("orders by severity, then earliest due date", () => {
    render(
      <AlertPanel
        emptyTitle="none"
        alerts={[
          alert({ key: "info", severity: "INFO", due_on: "2026-10-01" }),
          alert({
            key: "warn-late",
            severity: "WARNING",
            due_on: "2026-12-01",
          }),
          alert({ key: "crit", severity: "CRITICAL", due_on: "2026-12-31" }),
          alert({
            key: "warn-early",
            severity: "WARNING",
            due_on: "2026-11-01",
          }),
          alert({ key: "warn-undated", severity: "WARNING" }),
        ]}
      />,
    );
    const titles = screen
      .getAllByRole("listitem")
      .map((li) => within(li).getByText(/^(info|warn|crit)/).textContent);
    expect(titles).toEqual([
      "crit",
      "warn-early",
      "warn-late",
      "warn-undated",
      "info",
    ]);
  });

  it("shows severity as text and links the action with its query", () => {
    render(
      <AlertPanel
        emptyTitle="none"
        alerts={[
          alert({
            key: "short",
            type: "SHORTFALL",
            severity: "WARNING",
            amount: "1560.00",
            currency: "USD",
            action: {
              code: "COMPARE_FINANCING",
              label_en: "Compare financing options",
              label_bn: "x",
              route: "/app/financing",
              query: { amount: "1560.00", date: "2026-11-07" },
            },
          }),
        ]}
      />,
    );
    expect(screen.getByText("Warning")).toBeInTheDocument();
    expect(screen.getByText("$1,560.00")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Compare financing options" }),
    ).toHaveAttribute("href", "/app/financing?amount=1560.00&date=2026-11-07");
  });

  it("renders the empty state", () => {
    render(<AlertPanel emptyTitle="No alerts" alerts={[]} />);
    expect(screen.getByText("No alerts")).toBeInTheDocument();
  });
});
