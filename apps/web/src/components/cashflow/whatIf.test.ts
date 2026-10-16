import { describe, expect, it } from "vitest";

import { buildScenarioRequest, addDays, type WhatIfState } from "./whatIf";

const base: WhatIfState = {
  moveRef: "",
  moveOn: "",
  loanOn: false,
  loanAmount: "3835.00",
  loanDate: "2026-11-06",
  repayDate: "",
  repayAmount: "",
  removed: [],
};

describe("buildScenarioRequest", () => {
  it("sends nothing when there are no changes", () => {
    const r = buildScenarioRequest(base);
    expect(r.request).toBeNull();
    expect(r.hasChanges).toBe(false);
  });

  it("builds a move with party id", () => {
    const r = buildScenarioRequest(
      { ...base, moveRef: "cost:X:DUTY", moveOn: "2026-12-10" },
      "p1",
    );
    expect(r.request).toEqual({
      party_id: "p1",
      days: 90,
      moves: [{ ref: "cost:X:DUTY", on: "2026-12-10" }],
      removes: [],
      loans: [],
    });
  });

  it("builds a loan with optional repayment and removes", () => {
    const r = buildScenarioRequest({
      ...base,
      loanOn: true,
      repayDate: "2027-01-10",
      repayAmount: "4000.00",
      removed: ["a", "b"],
    });
    expect(r.request?.loans).toEqual([
      {
        amount: "3835.00",
        on: "2026-11-06",
        repay_on: "2027-01-10",
        repay_amount: "4000.00",
      },
    ]);
    expect(r.request?.removes).toEqual(["a", "b"]);
  });

  it("rejects bad decimals and dates without sending", () => {
    const r = buildScenarioRequest({
      ...base,
      loanOn: true,
      loanAmount: "12,5",
      loanDate: "2026-02-31",
    });
    expect(r.request).toBeNull();
    expect(r.errors).toEqual({
      loanAmount: "invalidDecimal",
      loanDate: "invalidDate",
    });
  });

  it("ignores a move on an item that is also switched off", () => {
    const r = buildScenarioRequest({
      ...base,
      moveRef: "a",
      moveOn: "2026-12-10",
      removed: ["a"],
    });
    expect(r.request?.moves).toEqual([]);
  });
});

describe("addDays", () => {
  it("steps across month ends", () => {
    expect(addDays("2026-11-01", -1)).toBe("2026-10-31");
  });
});
