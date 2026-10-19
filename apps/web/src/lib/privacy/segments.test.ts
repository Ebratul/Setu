import { describe, expect, it } from "vitest";

import { orderedCounts, protectedCount, segmentsToText, tokenize, typeMeta } from "./segments";

describe("privacy segment helpers", () => {
  it("tokenizes a masked payload into plain and token segments", () => {
    const segs = tokenize("Pay ⟦ACCT_1⟧ or call ⟦PHONE_2⟧ now");
    expect(segs.map((s) => [s.type, s.text])).toEqual([
      [null, "Pay "],
      ["ACCT", "⟦ACCT_1⟧"],
      [null, " or call "],
      ["PHONE", "⟦PHONE_2⟧"],
      [null, " now"],
    ]);
    expect(segmentsToText(segs)).toBe("Pay ⟦ACCT_1⟧ or call ⟦PHONE_2⟧ now");
    expect(protectedCount(segs)).toBe(2);
  });

  it("orders counts canonically, drops zeros and puts unknown types last", () => {
    expect(orderedCounts({ ACCT: 1, ZZZ: 2, NID: 3, PHONE: 0 })).toEqual([
      ["NID", 3],
      ["ACCT", 1],
      ["ZZZ", 2],
    ]);
  });

  it("gives every type an icon and a short code, with a fallback", () => {
    expect(typeMeta("NID").code).toBe("NID");
    expect(typeMeta("NOPE").icon).toBe("•");
  });
});
