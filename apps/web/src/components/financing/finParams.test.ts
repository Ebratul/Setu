import { describe, expect, it } from "vitest";

import { parseFinParams } from "./finParams";

const p = (q: string) => parseFinParams(new URLSearchParams(q));

describe("parseFinParams", () => {
  it("reads the dashboard shortfall link as shortfall mode with an amount", () => {
    expect(
      p("amount=1560.00&currency=USD&date=2026-11-07&deal=SETU-2026-0001"),
    ).toEqual({
      mode: "shortfall",
      deal: "SETU-2026-0001",
      amount: "1560.00",
      date: "2026-11-07",
      currency: "USD",
    });
  });
  it("reads order mode from the deal page link", () => {
    expect(p("deal=SETU-2026-0001&mode=order").mode).toBe("order");
  });
  it("prefill=shortfall wins over mode", () => {
    expect(p("mode=order&prefill=shortfall").mode).toBe("shortfall");
  });
  it("drops malformed values", () => {
    const r = p("amount=abc&date=tomorrow&currency=EUR&deal=a%20b");
    expect(r.amount).toBeUndefined();
    expect(r.date).toBeUndefined();
    expect(r.currency).toBeUndefined();
    expect(r.deal).toBeUndefined();
  });
});
