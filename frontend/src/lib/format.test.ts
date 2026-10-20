import { afterEach, describe, expect, it } from "vitest";

import { formatDate, formatMoney, formatPct, getDigits, loadDigits, setDigits } from "./format";

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

describe("digits preference", () => {
  afterEach(() => {
    setDigits("native");
    localStorage.clear();
  });
  it("defaults to native Bangla digits", () => {
    expect(getDigits()).toBe("native");
    expect(formatMoney("1200.5", "BDT", "bn")).toBe("৳১,২০০.৫০");
  });
  it("switches bn to Latin digits and persists", () => {
    setDigits("latin");
    expect(formatMoney("1200.5", "BDT", "bn")).toBe("৳1,200.50");
    expect(formatDate("2026-10-20", "bn")).toMatch(/2026/);
    expect(localStorage.getItem("setu_digits")).toBe("latin");
  });
  it("does not affect en or zh", () => {
    const en = formatMoney("1200.5", "USD", "en");
    const zh = formatMoney("1200.5", "USD", "zh");
    setDigits("latin");
    expect(formatMoney("1200.5", "USD", "en")).toBe(en);
    expect(formatMoney("1200.5", "USD", "zh")).toBe(zh);
  });
  it("loads the stored value", () => {
    localStorage.setItem("setu_digits", "latin");
    loadDigits();
    expect(getDigits()).toBe("latin");
  });
});
