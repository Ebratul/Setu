import { afterEach, describe, expect, it, vi } from "vitest";

describe("neon-auth route without env", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("returns 404 JSON and does not throw at import", async () => {
    vi.stubEnv("NEON_AUTH_BASE_URL", "");
    vi.stubEnv("NEON_AUTH_COOKIE_SECRET", "");
    vi.resetModules();
    const { GET, POST } = await import("./route");
    const ctx = { params: Promise.resolve({ path: ["get-session"] }) };
    for (const h of [GET, POST]) {
      const res = await h(new Request("http://localhost/neon-auth/get-session"), ctx);
      expect(res.status).toBe(404);
      expect(await res.json()).toMatchObject({ code: "AUTH_NOT_CONFIGURED" });
    }
  });
});
