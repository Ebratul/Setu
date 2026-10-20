import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import { attempt, authErrorKey, classifyApiError, safeNext } from "./flow";

describe("auth flow helpers", () => {
  it("keeps next inside the role area", () => {
    expect(safeNext("/app/deals", "BUYER")).toBe("/app/deals");
    expect(safeNext("https://evil.example", "BUYER")).toBe("/app");
    expect(safeNext("/app", "SUPPLIER")).toBe("/supplier");
  });

  it("classifies API error codes", () => {
    const e = (s: number, c: string) => new ApiError(s, "x", null, c);
    expect(classifyApiError(e(403, "EMAIL_NOT_VERIFIED"))).toEqual({ kind: "unverified" });
    expect(classifyApiError(e(403, "ACCOUNT_SUSPENDED"))).toEqual({ kind: "status", reason: "suspended" });
    expect(classifyApiError(e(401, "TOKEN_INVALID"))).toEqual({ kind: "message", key: "auth.err.session" });
    expect(classifyApiError(new Error("net"))).toEqual({ kind: "message", key: "auth.err.generic" });
  });

  it("maps SDK failures, thrown or returned", async () => {
    const thrown = await attempt(() => Promise.reject({ code: "invalid_credentials", status: 401 }));
    expect(authErrorKey(thrown.error)).toBe("auth.err.invalid");
    const returned = await attempt(() => Promise.resolve({ error: { code: "user_already_exists", status: 422 } }));
    expect(authErrorKey(returned.error)).toBe("auth.err.exists");
    expect(authErrorKey({ code: "validation_failed", status: 400, message: "" }, "otp")).toBe("auth.err.otp");
    expect(authErrorKey({ code: "bad_jwt", status: 401, message: "" }, "reset")).toBe("auth.err.resetToken");
    expect(authErrorKey({ code: null, status: 429, message: "" })).toBe("auth.err.tooMany");
  });
});
