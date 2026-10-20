import { beforeEach, describe, expect, it, vi } from "vitest";

const mode = vi.fn();
const getAccessToken = vi.fn();
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => mode(),
  getAccessToken: (o?: unknown) => getAccessToken(o),
  clearAccessToken: vi.fn(),
}));

import { apiGet } from "./client";

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
});
