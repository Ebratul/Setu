import { describe, expect, it } from "vitest";

import {
  RING_CIRCUMFERENCE,
  canSubmitOtp,
  digitsOnly,
  formatClock,
  ringState,
  secondsLeft,
} from "./approvalLogic";

describe("cooling-off countdown", () => {
  it("counts down from the server value at fetch time and never goes negative", () => {
    expect(secondsLeft(30, 1000, 1000)).toBe(30);
    expect(secondsLeft(30, 1000, 11_000)).toBe(20);
    expect(secondsLeft(30, 1000, 11_400)).toBe(20);
    expect(secondsLeft(30, 1000, 99_000)).toBe(0);
    expect(secondsLeft(null, 0, 5)).toBe(0);
  });

  it("maps elapsed time to the ring dashoffset", () => {
    expect(ringState(30, 30)).toEqual({ elapsed: 0, dashoffset: RING_CIRCUMFERENCE });
    expect(ringState(15, 30).dashoffset).toBeCloseTo(RING_CIRCUMFERENCE / 2);
    expect(ringState(0, 30)).toEqual({ elapsed: 1, dashoffset: 0 });
    expect(ringState(0, null).elapsed).toBe(1);
  });

  it("formats m:ss", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65)).toBe("1:05");
  });
});

describe("OTP submit rule", () => {
  const ok = { left: 0, code: "123456", locked: false, busy: false };
  it("needs the pause over AND six digits", () => {
    expect(canSubmitOtp(ok)).toBe(true);
    expect(canSubmitOtp({ ...ok, left: 3 })).toBe(false);
    expect(canSubmitOtp({ ...ok, code: "12345" })).toBe(false);
    expect(canSubmitOtp({ ...ok, locked: true })).toBe(false);
    expect(canSubmitOtp({ ...ok, busy: true })).toBe(false);
  });
  it("keeps only digits, at most six", () => {
    expect(digitsOnly(" 12 34-5678 ")).toBe("123456");
  });
});
