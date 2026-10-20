import { beforeEach, describe, expect, it, vi } from "vitest";

const mode = vi.fn();
const getAccessToken = vi.fn();
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => mode(),
  getAccessToken: (o?: unknown) => getAccessToken(o),
  clearAccessToken: vi.fn(),
}));

import { ACCOUNT_BLOCK_EVENT, apiGet, apiPut, NOT_VERIFIED_EVENT } from "./client";

const problem = (status: number, code: string) =>
  new Response(JSON.stringify({ detail: "x", code }), { status });
const ok = () => new Response(JSON.stringify({ ok: true }), { status: 200 });

describe("api client auth", () => {
  beforeEach(() => {
    mode.mockReset();
    getAccessToken.mockReset();
  });

  it("sends no Authorization header in demo mode", async () => {
    mode.mockResolvedValue("demo");
    const f = vi.fn().mockResolvedValue(ok());
    vi.stubGlobal("fetch", f);
    await apiGet("/x");
    expect(getAccessToken).not.toHaveBeenCalled();
    expect(f.mock.calls[0][1].headers.Authorization).toBeUndefined();
    expect(f.mock.calls[0][1].credentials).toBe("same-origin");
  });

  it("attaches the bearer in neon mode", async () => {
    mode.mockResolvedValue("neon");
    getAccessToken.mockResolvedValue("tok1");
    const f = vi.fn().mockResolvedValue(ok());
    vi.stubGlobal("fetch", f);
    await apiGet("/x");
    expect(f.mock.calls[0][1].headers.Authorization).toBe("Bearer tok1");
  });

  it("refreshes once and retries on TOKEN_INVALID", async () => {
    mode.mockResolvedValue("neon");
    getAccessToken.mockResolvedValueOnce("old").mockResolvedValue("new");
    const f = vi.fn().mockResolvedValueOnce(problem(401, "TOKEN_INVALID")).mockResolvedValueOnce(ok());
    vi.stubGlobal("fetch", f);
    await expect(apiGet("/x")).resolves.toEqual({ ok: true });
    expect(f).toHaveBeenCalledTimes(2);
    expect(getAccessToken).toHaveBeenNthCalledWith(2, { force: true });
    expect(f.mock.calls[1][1].headers.Authorization).toBe("Bearer new");
  });

  it("does not retry twice", async () => {
    mode.mockResolvedValue("neon");
    getAccessToken.mockResolvedValue("t");
    const f = vi.fn().mockImplementation(async () => problem(401, "UNAUTHENTICATED"));
    vi.stubGlobal("fetch", f);
    await expect(apiGet("/x")).rejects.toMatchObject({ status: 401, code: "UNAUTHENTICATED" });
    expect(f).toHaveBeenCalledTimes(2);
  });

  it("does not retry other 4xx codes", async () => {
    mode.mockResolvedValue("neon");
    getAccessToken.mockResolvedValue("t");
    const f = vi.fn().mockImplementation(async () => problem(403, "ACCOUNT_PENDING"));
    vi.stubGlobal("fetch", f);
    await expect(apiGet("/x")).rejects.toMatchObject({ code: "ACCOUNT_PENDING" });
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("announces 403 ACCOUNT_NOT_VERIFIED once and still throws the typed error", async () => {
    mode.mockResolvedValue("demo");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(problem(403, "ACCOUNT_NOT_VERIFIED")),
    );
    const seen = vi.fn();
    window.addEventListener(NOT_VERIFIED_EVENT, seen);
    await expect(apiGet("/x")).rejects.toMatchObject({
      status: 403,
      code: "ACCOUNT_NOT_VERIFIED",
    });
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener(NOT_VERIFIED_EVENT, seen);
  });

  it("sends PUT with a JSON body", async () => {
    mode.mockResolvedValue("demo");
    const f = vi.fn().mockResolvedValue(ok());
    vi.stubGlobal("fetch", f);
    await apiPut("/x", { a: 1 });
    expect(f.mock.calls[0][1].method).toBe("PUT");
    expect(f.mock.calls[0][1].body).toBe('{"a":1}');
  });

  it("parses per-field validation errors from a 422 problem body", async () => {
    mode.mockResolvedValue("demo");
    const body = { code: "VALIDATION_FAILED", errors: [{ field: "bank.swift", code: "INVALID_SWIFT", message: "x" }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 422 })));
    await expect(apiGet("/x")).rejects.toMatchObject({ fields: [{ field: "bank.swift", code: "INVALID_SWIFT" }] });
  });

  it("announces ACCOUNT_SUSPENDED and MFA_REQUIRED, but not for /auth/ routes", async () => {
    mode.mockResolvedValue("demo");
    const seen = vi.fn();
    window.addEventListener(ACCOUNT_BLOCK_EVENT, seen);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(problem(403, "ACCOUNT_SUSPENDED"))));
    await expect(apiGet("/deals")).rejects.toBeTruthy();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(problem(403, "MFA_REQUIRED"))));
    await expect(apiGet("/auth/mfa/totp/disable")).rejects.toBeTruthy();
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener(ACCOUNT_BLOCK_EVENT, seen);
  });
});
