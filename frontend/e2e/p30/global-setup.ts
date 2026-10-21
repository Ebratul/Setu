import { AGENTS, MOCK_AUTH_BASE, MOCK_ORIGIN } from "./env";

// Warm each backend's JWKS cache with one sequential request. Without it the first burst of
// concurrent calls after a cold start can get 503 (JwksCache.key_for: losers of the fetch race see
// no keys). That is an app bug, reported separately; this keeps the suite about P30 behaviour.
export default async function globalSetup() {
  const created = await fetch(`${MOCK_ORIGIN}/__test/accounts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "warmup@setu-e2e.test" }),
  });
  const { id } = (await created.json()) as { id: string };
  const h = { "x-mock-account": id, "content-type": "application/json" };
  await fetch(`${MOCK_AUTH_BASE}/sign-in/social`, { method: "POST", headers: h, body: JSON.stringify({ provider: "google" }) });
  const { token } = (await (await fetch(`${MOCK_AUTH_BASE}/token`, { headers: h })).json()) as { token: string };
  for (const a of Object.values(AGENTS)) {
    await fetch(`${a.url}/auth/session`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  }
}
