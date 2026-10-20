import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { demoErrorKind, withRateRetry } from "./demo";

describe("demoErrorKind", () => {
  it("maps the documented sandbox failures", () => {
    expect(demoErrorKind(new ApiError(410, "x", null, "SANDBOX_EXPIRED"))).toBe("expired");
    expect(demoErrorKind(new ApiError(410, "x"))).toBe("expired");
    expect(demoErrorKind(new ApiError(429, "x", null, "SANDBOX_RATE_LIMIT", 3))).toBe("rate");
    expect(demoErrorKind(new ApiError(503, "x", null, "SANDBOX_CAPACITY"))).toBe("capacity");
    expect(demoErrorKind(new ApiError(404, "x", null, "SANDBOX_REQUIRED"))).toBe("required");
    expect(demoErrorKind(new ApiError(500, "x"))).toBe("other");
    expect(demoErrorKind(new TypeError("Failed to fetch"))).toBe("network");
  });
});

describe("withRateRetry", () => {
  it("retries once after Retry-After on a 429", async () => {
    const fn = vi.fn().mockRejectedValueOnce(new ApiError(429, "x", null, "SANDBOX_RATE_LIMIT", 2)).mockResolvedValue("ok");
    const sleep = vi.fn().mockResolvedValue(undefined);
    const wait = vi.fn();
    await expect(withRateRetry(fn, sleep, wait)).resolves.toBe("ok");
    expect(sleep).toHaveBeenCalledWith(2000);
    expect(wait).toHaveBeenCalledWith(2);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("defaults to 5 s, caps at 30 s and gives up after the second 429", async () => {
    const err = new ApiError(429, "x", null, null, 120);
    const fn = vi.fn().mockRejectedValue(err);
    const sleep = vi.fn().mockResolvedValue(undefined);
    await expect(withRateRetry(fn, sleep)).rejects.toBe(err);
    expect(sleep).toHaveBeenCalledWith(30000);
    expect(fn).toHaveBeenCalledTimes(2);
    const sleep2 = vi.fn().mockResolvedValue(undefined);
    await withRateRetry(vi.fn().mockRejectedValueOnce(new ApiError(429, "x")).mockResolvedValue(1), sleep2);
    expect(sleep2).toHaveBeenCalledWith(5000);
  });

  it("does not retry other errors", async () => {
    const err = new ApiError(410, "x", null, "SANDBOX_EXPIRED");
    const fn = vi.fn().mockRejectedValue(err);
    await expect(withRateRetry(fn)).rejects.toBe(err);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
