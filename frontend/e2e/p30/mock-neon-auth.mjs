// Local mock of Neon Auth (Better Auth) for the P30 e2e suite. Plays "Google": sign-in/social
// signs the pre-registered account in without leaving localhost. Serves the EdDSA JWKS the
// backend verifies against and mints access JWTs (iss = aud = this origin).
// Test control API (not part of Neon): POST /__test/accounts, GET /__test/health.
import { createServer } from "node:http";
import { generateKeyPairSync, randomUUID, sign } from "node:crypto";

const PORT = Number(process.env.MOCK_NEON_PORT ?? 4010);
const ORIGIN = `http://127.0.0.1:${PORT}`;
const BASE = "/neondb/auth";
const TOKEN_TTL_S = Number(process.env.MOCK_NEON_TOKEN_TTL ?? 900);

const { privateKey, publicKey } = generateKeyPairSync("ed25519");
const KID = `e2e-${randomUUID().slice(0, 8)}`;
const jwk = { ...publicKey.export({ format: "jwk" }), kid: KID, alg: "EdDSA", use: "sig" };

/** @type {Map<string, {id:string,email:string,name:string,emailVerified:boolean}>} */
const accounts = new Map();
/** Account ids with a live session. The browser cookie is replaced by the x-mock-account header the test adds. */
const sessions = new Set();

const b64u = (b) => Buffer.from(b).toString("base64url");

function mintJwt(a) {
  const now = Math.floor(Date.now() / 1000);
  const head = b64u(JSON.stringify({ alg: "EdDSA", typ: "JWT", kid: KID }));
  const body = b64u(
    JSON.stringify({
      sub: a.id, email: a.email, name: a.name, emailVerified: a.emailVerified,
      iss: ORIGIN, aud: ORIGIN, iat: now, exp: now + TOKEN_TTL_S,
    }),
  );
  const sig = sign(null, Buffer.from(`${head}.${body}`), privateKey);
  return `${head}.${body}.${b64u(sig)}`;
}

function send(res, status, body, headers = {}) {
  const payload = body === undefined ? "" : JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(payload);
}

async function readJson(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8");
  try { return raw ? JSON.parse(raw) : {}; } catch { return {}; }
}

function sessionOf(req) {
  const id = String(req.headers["x-mock-account"] ?? "");
  const acc = accounts.get(id);
  return acc && sessions.has(id) ? { sid: `sess_${id}`, acc } : null;
}

const userOf = (a) => ({
  id: a.id, email: a.email, name: a.name, emailVerified: a.emailVerified, image: null,
  createdAt: "2026-10-01T00:00:00.000Z", updatedAt: "2026-10-01T00:00:00.000Z",
});

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", ORIGIN);
  const p = url.pathname;
  try {
    if (p === "/__test/health") return send(res, 200, { ok: true, kid: KID });
    if (p === "/__test/accounts" && req.method === "POST") {
      const b = await readJson(req);
      const id = `neon_${randomUUID()}`;
      accounts.set(id, { id, email: String(b.email).toLowerCase(), name: String(b.name ?? "E2E User"), emailVerified: b.emailVerified !== false });
      return send(res, 201, { id });
    }
    if (p === `${BASE}/.well-known/jwks.json` || p === "/.well-known/jwks.json") return send(res, 200, { keys: [jwk] });
    if (!p.startsWith(`${BASE}/`)) return send(res, 404, { message: "not found" });
    const route = p.slice(BASE.length);

    if (route === "/sign-in/social" && req.method === "POST") {
      const b = await readJson(req);
      const acc = accounts.get(String(req.headers["x-mock-account"] ?? ""));
      if (!acc || b.provider !== "google") return send(res, 400, { message: "unknown account", code: "INVALID_PROVIDER" });
      sessions.add(acc.id);
      return send(res, 200, { url: b.callbackURL ?? `${ORIGIN}/`, redirect: true });
    }
    if (route === "/get-session") {
      const s = sessionOf(req);
      if (!s) return send(res, 200, null);
      const exp = new Date(Date.now() + 3600_000).toISOString();
      return send(res, 200,
        { session: { id: s.sid, token: s.sid, userId: s.acc.id, expiresAt: exp, createdAt: exp, updatedAt: exp }, user: userOf(s.acc) },
        { "set-auth-jwt": mintJwt(s.acc) });
    }
    if (route === "/token") {
      const s = sessionOf(req);
      if (!s) return send(res, 401, { message: "Unauthorized", code: "UNAUTHORIZED" });
      return send(res, 200, { token: mintJwt(s.acc) });
    }
    if (route === "/sign-out" && req.method === "POST") {
      const s = sessionOf(req);
      if (s) sessions.delete(s.acc.id);
      return send(res, 200, { success: true });
    }
    if (route === "/list-sessions") return send(res, 200, []);
    if (route.startsWith("/revoke-")) return send(res, 200, { status: true });
    return send(res, 404, { message: `mock neon auth: ${route} not implemented`, code: "NOT_FOUND" });
  } catch (e) {
    return send(res, 500, { message: String(e) });
  }
});

server.listen(PORT, "127.0.0.1", () => console.log(`mock neon auth on ${ORIGIN}${BASE}`));
