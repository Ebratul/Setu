import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { parseEvalResults } from "@/lib/evalResults";

import { ResultsBand } from "./ResultsBand";

const ok = parseEvalResults({
  split: "dev",
  generatedAt: "x",
  metrics: {
    attackSuccessOff: { value: 1, total: 13, unit: "percent", source: "f" },
    attackSuccessOn: { value: 0, total: 13, unit: "percent", source: "f" },
    falsePositives: { value: 0, total: 300, unit: "count", source: "f" },
  },
});

describe("ResultsBand", () => {
  it("shows Coming soon for the whole band when the loader returns null", () => {
    render(<ResultsBand results={null} />);
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.queryByTestId("metric-attackSuccessOn")).toBeNull();
  });

  it("shows numbers where present and Coming soon where a metric is missing", () => {
    render(<ResultsBand results={ok} />);
    expect(within(screen.getByTestId("metric-attackSuccessOff")).getByText("100%")).toBeInTheDocument();
    expect(within(screen.getByTestId("metric-attackSuccessOn")).getByText("0%")).toBeInTheDocument();
    expect(within(screen.getByTestId("metric-falsePositives")).getByText("0 of 300")).toBeInTheDocument();
    expect(within(screen.getByTestId("metric-fraudRecall")).getByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByText(/test split has not been run/i)).toBeInTheDocument();
  });

  it("explains how each number was measured", () => {
    render(<ResultsBand results={ok} />);
    const tip = within(screen.getByTestId("metric-attackSuccessOff")).getByRole("button");
    expect(tip).toHaveAccessibleName(/13 synthetic injection attacks, dev split/);
  });
});
