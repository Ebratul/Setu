import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KpiCard } from "./KpiCard";

describe("KpiCard", () => {
  it.each([
    ["healthy", "Healthy", "success", "border-success"],
    ["thin", "Thin", "warning", "border-warning"],
    ["low", "Low", "danger", "border-danger"],
  ] as const)(
    "%s band uses %s tone with a text label",
    (band, label, tone, cls) => {
      render(<KpiCard label="Gross margin" value="18.01%" band={band} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      const card = screen.getByTestId("kpi-card");
      expect(card).toHaveAttribute("data-tone", tone);
      expect(card.className).toContain(cls);
    },
  );

  it("is neutral without a band", () => {
    render(<KpiCard label="Landed cost" value="$11,200.00" />);
    expect(screen.getByTestId("kpi-card")).toHaveAttribute(
      "data-tone",
      "neutral",
    );
    expect(screen.queryByText("Healthy")).toBeNull();
  });
});
