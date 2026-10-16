import { describe, expect, it } from "vitest";

import { formatMoney, formatPct } from "./format";

describe("formatMoney", () => {
  it("formats the three currencies with separators", () => {
    expect(formatMoney("11200.00", "USD", "en")).toBe("$11,200.00");
    expect(formatMoney("1373008.00", "BDT", "en")).toBe("৳1,373,008.00");
    expect(formatMoney("79508.80", "CNY", "en")).toBe("¥79,508.80");
  });
  it("keeps up to 4 decimals for per-unit values", () => {
    expect(formatMoney("171.626", "USD", "en")).toBe("$171.626");
    expect(formatMoney("0.0459", "USD", "en")).toBe("$0.0459");
    expect(formatMoney("1.4", "USD", "en")).toBe("$1.40");
  });
  it("uses Bangla digits for bn", () => {
    expect(formatMoney("11200.00", "BDT", "bn")).toBe("৳১১,২০০.০০");
  });
  it("formats percents", () => {
    expect(formatPct("18.01")).toBe("18.01%");
  });
});
