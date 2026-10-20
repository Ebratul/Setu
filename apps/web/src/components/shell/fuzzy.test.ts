import { describe, expect, it } from "vitest";

import { fuzzyScore } from "./fuzzy";

describe("fuzzyScore", () => {
  it("matches everything for an empty query", () => {
    expect(fuzzyScore("", "Deals")).toBe(0);
  });
  it("prefers substrings, then subsequences, else null", () => {
    const sub = fuzzyScore("cash", "Cash Flow") ?? -1;
    const seq = fuzzyScore("cfl", "Cash Flow") ?? -1;
    expect(sub).toBeGreaterThan(seq);
    expect(seq).toBeGreaterThan(0);
    expect(fuzzyScore("zzz", "Cash Flow")).toBeNull();
  });
  it("works for Bangla text", () => {
    expect(fuzzyScore("অনুমোদন", "অনুমোদন")).not.toBeNull();
  });
});
