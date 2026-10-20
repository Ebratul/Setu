import { describe, expect, it } from "vitest";

import { SCRIPT } from "./fixtures";
import {
  dwellMs,
  embedUrl,
  flattenScenes,
  formatCountdown,
  indexForStep,
  nextIndex,
  parseMode,
  parseStepParam,
  prevIndex,
  progressOf,
  roleOfEmail,
} from "./demoModel";

const flat = flattenScenes(SCRIPT);

describe("scene flattening and navigation", () => {
  it("orders steps then scenes and numbers the position inside a step", () => {
    expect(flat.map((f) => f.key)).toEqual(["1.1", "2.1", "2.2", "3.1"]);
    expect(flat.map((f) => f.index)).toEqual([0, 1, 2, 3]);
    expect(progressOf(flat[2])).toEqual({ step: 2, pos: 2, count: 2 });
  });

  it("moves next/previous without wrapping", () => {
    expect(nextIndex(flat, 0)).toBe(1);
    expect(nextIndex(flat, 3)).toBeNull();
    expect(prevIndex(0)).toBeNull();
    expect(prevIndex(3)).toBe(2);
  });

  it("deep link ?step=N lands on scene 1 of that step", () => {
    expect(indexForStep(flat, 3)).toBe(3);
    expect(indexForStep(flat, 2)).toBe(1);
    expect(indexForStep(flat, 9)).toBeNull();
    expect(parseStepParam("3", flat)).toBe(3);
    expect(parseStepParam("9", flat)).toBeNull();
    expect(parseStepParam("abc", flat)).toBeNull();
    expect(parseStepParam(null, flat)).toBeNull();
  });
});

describe("auto-play timing", () => {
  it("uses 7 s as the base and scales with speed", () => {
    expect(dwellMs(40, 1)).toBe(7000);
    expect(dwellMs(40, 2)).toBe(3500);
    expect(dwellMs(40, 1.5)).toBe(4667);
  });
  it("dwells longer for long captions, capped at 16 s", () => {
    expect(dwellMs(190, 1)).toBe(11000);
    expect(dwellMs(5000, 1)).toBe(16000);
    expect(dwellMs(5000, 2)).toBe(8000);
  });
  it("never divides by zero", () => {
    expect(dwellMs(10, 0)).toBe(7000);
  });
});

describe("helpers", () => {
  it("appends embed=1 with the right separator", () => {
    expect(embedUrl("/app/cashflow")).toBe("/app/cashflow?embed=1");
    expect(embedUrl("/app/chat?thread=abc")).toBe("/app/chat?thread=abc&embed=1");
  });
  it("formats the expiry countdown", () => {
    expect(formatCountdown(3_725_000)).toBe("1:02:05");
    expect(formatCountdown(65_000)).toBe("01:05");
    expect(formatCountdown(-5)).toBe("00:00");
  });
  it("parses the mode and role", () => {
    expect(parseMode("presenter")).toBe("presenter");
    expect(parseMode("record")).toBe("record");
    expect(parseMode("x")).toBe("normal");
    expect(roleOfEmail("huaxin@demo.setu")).toBe("supplier");
    expect(roleOfEmail("nobody@x")).toBeNull();
  });
});
