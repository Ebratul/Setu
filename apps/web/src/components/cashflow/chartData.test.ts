import { describe, expect, it } from "vitest";

import { shortfallRanges, type ChartPoint } from "./chartData";

const p = (on: string, below: boolean): ChartPoint => ({
  on,
  closing: 0,
  closingText: "0.00",
  below,
  cost: false,
});

describe("shortfallRanges", () => {
  it("groups consecutive below-buffer days", () => {
    const pts = [
      p("01", false),
      p("02", true),
      p("03", true),
      p("04", false),
      p("05", true),
    ];
    expect(shortfallRanges(pts)).toEqual([
      { x1: "02", x2: "03" },
      { x1: "05", x2: "05" },
    ]);
  });
  it("is empty when no day is below", () => {
    expect(shortfallRanges([p("01", false)])).toEqual([]);
  });
});
