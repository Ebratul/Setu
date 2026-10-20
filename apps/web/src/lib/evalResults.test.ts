import { describe, expect, it } from "vitest";

import { parseEvalResults } from "./evalResults";

const metric = { value: 0.5, total: 10, unit: "percent", source: "x" };

describe("parseEvalResults", () => {
  it("accepts a dev file and nulls missing metrics", () => {
    const r = parseEvalResults({ split: "dev", metrics: { detectionRecall: metric } });
    expect(r?.metrics.detectionRecall?.value).toBe(0.5);
    expect(r?.metrics.fraudRecall).toBeNull();
  });
  it("rejects test split, garbage and empty metric sets", () => {
    expect(parseEvalResults({ split: "test", metrics: { detectionRecall: metric } })).toBeNull();
    expect(parseEvalResults(null)).toBeNull();
    expect(parseEvalResults({ split: "dev", metrics: {} })).toBeNull();
    expect(parseEvalResults({ split: "dev", metrics: { detectionRecall: { ...metric, value: 2 } } })).toBeNull();
  });
});
