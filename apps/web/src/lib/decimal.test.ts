import { describe, expect, it } from "vitest";

import { isZero, mulDecimal, sumDecimals } from "./decimal";

describe("decimal strings", () => {
  it("multiplies exactly where floats would drift", () => {
    expect(mulDecimal("0.1", "3")).toBe("0.30");
    expect(mulDecimal("8000", "1.20")).toBe("9600.00");
    expect(mulDecimal("1234567.89", "0.0001")).toBe("123.456789");
    expect(mulDecimal("1.1", "1.1")).toBe("1.21");
  });
  it("rejects bad input", () => {
    expect(mulDecimal("abc", "1")).toBeNull();
    expect(mulDecimal("1e3", "1")).toBeNull();
    expect(mulDecimal("-1", "1")).toBeNull();
  });
  it("sums percents exactly", () => {
    expect(sumDecimals(["33.3", "33.3", "33.4"])).toBe("100");
    expect(sumDecimals(["0.1", "0.2"])).toBe("0.3");
    expect(sumDecimals(["x"])).toBeNull();
  });
  it("detects zero", () => {
    expect(isZero("0")).toBe(true);
    expect(isZero("0.00")).toBe(true);
    expect(isZero("0.01")).toBe(false);
  });
});
