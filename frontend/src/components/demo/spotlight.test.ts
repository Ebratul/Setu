import { describe, expect, it } from "vitest";

import { computeSpotlight, fitScale } from "./spotlight";

const stage = { width: 1000, height: 600 };
const bubble = { width: 300, height: 80 };

describe("computeSpotlight", () => {
  it("centres the caption when the element was not found", () => {
    const s = computeSpotlight(null, stage, bubble);
    expect(s.mode).toBe("center");
    expect(s.bubble).toEqual({ left: 350, top: 260, width: 300, height: 80 });
  });

  it("pads the target and puts the bubble below when there is room", () => {
    const s = computeSpotlight({ left: 100, top: 100, width: 200, height: 50 }, stage, bubble);
    if (s.mode !== "cutout") throw new Error("expected cutout");
    expect(s.hole).toEqual({ left: 92, top: 92, width: 216, height: 66 });
    expect(s.placement).toBe("below");
    expect(s.bubble.top).toBe(92 + 66 + 12);
  });

  it("flips above when the target is near the bottom", () => {
    const s = computeSpotlight({ left: 100, top: 500, width: 200, height: 60 }, stage, bubble);
    if (s.mode !== "cutout") throw new Error("expected cutout");
    expect(s.placement).toBe("above");
    expect(s.bubble.top + s.bubble.height).toBeLessThanOrEqual(s.hole.top);
  });

  it("goes beside a tall element and always stays inside the stage", () => {
    const s = computeSpotlight({ left: 20, top: 10, width: 200, height: 580 }, stage, bubble);
    if (s.mode !== "cutout") throw new Error("expected cutout");
    expect(s.placement).toBe("right");
    for (const r of [s.bubble]) {
      expect(r.left).toBeGreaterThanOrEqual(0);
      expect(r.top).toBeGreaterThanOrEqual(0);
      expect(r.left + r.width).toBeLessThanOrEqual(stage.width);
      expect(r.top + r.height).toBeLessThanOrEqual(stage.height);
    }
  });

  it("clips the hole to the stage and falls back inside for a huge element", () => {
    const s = computeSpotlight({ left: -50, top: -50, width: 2000, height: 2000 }, stage, bubble);
    if (s.mode !== "cutout") throw new Error("expected cutout");
    expect(s.hole).toEqual({ left: 0, top: 0, width: 1000, height: 600 });
    expect(s.placement).toBe("inside");
  });

  it("treats an empty or off-stage rect as not found", () => {
    expect(computeSpotlight({ left: 10, top: 10, width: 0, height: 0 }, stage, bubble).mode).toBe("center");
    expect(computeSpotlight({ left: 5000, top: 5000, width: 10, height: 10 }, stage, bubble).mode).toBe("center");
  });

  it("shrinks the bubble on a very narrow stage", () => {
    const s = computeSpotlight(null, { width: 200, height: 300 }, bubble);
    expect(s.bubble.width).toBeLessThanOrEqual(184);
  });
});

describe("fitScale", () => {
  it("fits 1920x1080 into the viewport", () => {
    expect(fitScale({ width: 960, height: 540 })).toBe(0.5);
    expect(fitScale({ width: 1920, height: 540 })).toBe(0.5);
    expect(fitScale({ width: 0, height: 0 })).toBe(1);
  });
});
