import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.unmock("@/lib/auth/client");
const token = vi.fn();
const getSession = vi.fn();
vi.mock("@neondatabase/auth", () => ({
  createAuthClient: () => ({ token, getSession, signOut: vi.fn() }),
}));
vi.mock("@neondatabase/auth/react/adapters", () => ({
  BetterAuthReactAdapter: () => ({}),
}));

import {
  clearAccessToken,
  getAccessToken,
  getAuthMode,
  resetAuthStateForTests,
} from "./client";

function jwt(expSec: number) {
  const body = btoa(JSON.stringify({ exp: expSec })).replace(/=+$/, "");
  return `h.${body}.s`;
}
const nowSec = () => Math.floor(Date.now() / 1000);

describe("access token cache", () => {
  beforeEach(() => {
    resetAuthStateForTests();
    token.mockReset();
    getSession.mockReset();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        const t = (await token())?.data?.token;
        return t
          ? Response.json({ token: t })
          : new Response("{}", { status: 401 });
      }),
    );
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reuses a fresh token", async () => {
    token.mockResolvedValue({ data: { token: jwt(nowSec() + 900) } });
    const a = await getAccessToken();
    const b = await getAccessToken();
    expect(a).toBe(b);
    expect(token).toHaveBeenCalledTimes(1);
  });

  it("refreshes inside the 60 s margin", async () => {
    token.mockResolvedValueOnce({ data: { token: jwt(nowSec() + 30) } });
    token.mockResolvedValueOnce({ data: { token: jwt(nowSec() + 900) } });
    await getAccessToken();
    await getAccessToken();
    expect(token).toHaveBeenCalledTimes(2);
  });

  it("shares one request between concurrent callers", async () => {
    token.mockResolvedValue({ data: { token: jwt(nowSec() + 900) } });
    await Promise.all([
      getAccessToken(),
      getAccessToken(),
      getAccessToken({ force: true }),
    ]);
    expect(token).toHaveBeenCalledTimes(1);
  });

  it("forces a refresh and clears on sign-out", async () => {
    token.mockResolvedValue({ data: { token: jwt(nowSec() + 900) } });
    await getAccessToken();
    await getAccessToken({ force: true });
    expect(token).toHaveBeenCalledTimes(2);
    clearAccessToken();
    await getAccessToken();
    expect(token).toHaveBeenCalledTimes(3);
  });

  it("returns null when signed out", async () => {
    token.mockResolvedValue({ data: null, error: { status: 401 } });
    expect(await getAccessToken()).toBeNull();
  });

  it("takes the JWT the SDK puts on the session, without calling the token endpoint", async () => {
    getSession
      .mockReset()
      .mockResolvedValue({
        data: { session: { token: jwt(nowSec() + 900) } },
      });
    token.mockReset();
    expect(await getAccessToken()).toMatch(/^h\./);
    expect(token).not.toHaveBeenCalled();
  });

  it("falls back to the token endpoint when the session carries no JWT", async () => {
    getSession
      .mockReset()
      .mockResolvedValue({
        data: { session: { token: "opaque-session-id" } },
      });
    token
      .mockReset()
      .mockResolvedValue({ data: { token: jwt(nowSec() + 900) } });
    expect(await getAccessToken()).toMatch(/^h\./);
    expect(token).toHaveBeenCalledTimes(1);
  });
});

describe("getAuthMode", () => {
  beforeEach(() => resetAuthStateForTests());
  it("fetches once and caches", async () => {
    const f = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ mode: "neon" })));
    vi.stubGlobal("fetch", f);
    expect(await getAuthMode()).toBe("neon");
    expect(await getAuthMode()).toBe("neon");
    expect(f).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
  it("retries after a failure", async () => {
    const f = vi
      .fn()
      .mockResolvedValueOnce(new Response("x", { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ mode: "demo" })));
    vi.stubGlobal("fetch", f);
    await expect(getAuthMode()).rejects.toThrow();
    expect(await getAuthMode()).toBe("demo");
    vi.unstubAllGlobals();
  });
});
