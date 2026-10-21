type NeonAuthServer = ReturnType<
  typeof import("@neondatabase/auth/next/server").createNeonAuth
>;

let instance: NeonAuthServer | null | undefined;

/**
 * Lazy so that deployments without Neon Auth env (demo/judge) never load the SDK or throw at import time.
 * Resolves to null when NEON_AUTH_BASE_URL / NEON_AUTH_COOKIE_SECRET are unset.
 */
export async function getNeonAuthServer(): Promise<NeonAuthServer | null> {
  if (instance !== undefined) return instance;
  const baseUrl = process.env.NEON_AUTH_BASE_URL?.trim();
  const secret = process.env.NEON_AUTH_COOKIE_SECRET?.trim();
  if (!baseUrl || !secret) return null;
  const { createNeonAuth } = await import("@neondatabase/auth/next/server");
  instance = createNeonAuth({ baseUrl, cookies: { secret } });
  return instance;
}
