import { createHmac, randomBytes } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, type BrowserContext, type Page } from "@playwright/test";

import { AGENTS, MOCK_AUTH_BASE, MOCK_ORIGIN, type AgentKey } from "./env";

// ---------------------------------------------------------------- i18n lookup (text comes from the app's own JSON)
type Dict = { [k: string]: string | Dict };
const I18N = path.resolve(__dirname, "../../src/i18n");
function flatten(d: Dict, prefix = "", out: Record<string, string> = {}) {
  for (const [k, v] of Object.entries(d)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else flatten(v, key, out);
  }
  return out;
}
const dicts: Record<string, Record<string, string>> = {};
export type Lang = "en" | "bn" | "zh";
function dict(lang: Lang) {
  if (!dicts[lang]) {
    const files = [`${lang}.json`, ...fs.readdirSync(path.join(I18N, "parts")).filter((f) => f.endsWith(`.${lang}.json`)).map((f) => `parts/${f}`)];
    dicts[lang] = Object.assign({}, ...files.map((f) => flatten(JSON.parse(fs.readFileSync(path.join(I18N, f), "utf8")) as Dict)));
  }
  return dicts[lang];
}
/** The app's own string for `key`; fails loudly if the key is gone so a rename cannot silently weaken a test. */
export function tr(key: string, lang: Lang = "en", vars: Record<string, string | number> = {}): string {
  const raw = dict(lang)[key];
  if (raw === undefined) throw new Error(`missing i18n key ${lang}:${key}`);
  return raw.replace(/\{(\w+)\}/g, (_m, name: string) => String(vars[name] ?? `{${name}}`));
}

// ---------------------------------------------------------------- stack wiring
/** Sends this context's /api/* calls to the chosen e2e backend (the web app's rewrite may point elsewhere). */
export async function useBackend(context: BrowserContext, key: AgentKey = "A") {
  await context.route("**/api/**", async (route) => {
    const u = new URL(route.request().url());
    const target = `${AGENTS[key].url}${u.pathname.replace(/^\/api/, "")}${u.search}`;
    await route.fulfill({ response: await route.fetch({ url: target }) });
  });
}

export type GoogleAccount = { id: string; email: string };

let counter = 0;
export function uniqueEmail(prefix: string) {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}${counter}${randomBytes(2).toString("hex")}@setu-e2e.test`;
}

/** Registers a Google identity in the mock and routes the page's /neon-auth/* calls to it. */
export async function mockGoogleAccount(
  context: BrowserContext,
  opts: { email?: string; name?: string; emailVerified?: boolean } = {},
): Promise<GoogleAccount> {
  const email = opts.email ?? uniqueEmail("user");
  const res = await fetch(`${MOCK_ORIGIN}/__test/accounts`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, name: opts.name ?? "E2E Person", emailVerified: opts.emailVerified ?? true }),
  });
  const { id } = (await res.json()) as { id: string };
  await context.route("**/neon-auth/**", async (route) => {
    const req = route.request();
    const rest = new URL(req.url()).pathname.replace(/^\/neon-auth/, "");
    const search = new URL(req.url()).search;
    const upstream = await route.fetch({ url: `${MOCK_AUTH_BASE}${rest}${search}`, headers: { ...req.headers(), "x-mock-account": id } });
    await route.fulfill({ response: upstream });
  });
  return { id, email };
}

/** Clicks "Continue with Google" on /login and waits for the app to open the Setu session and route on. */
export async function googleSignIn(page: Page, lang: Lang = "en") {
  await page.goto("/login");
  await page.getByRole("button", { name: tr("lg.google", lang), exact: true }).click();
}

/** Bearer JWT for the signed-in mock account (what the app sends to the API). */
export async function accessToken(page: Page): Promise<string> {
  return page.evaluate(async () => {
    const r = await fetch("/neon-auth/token", { credentials: "same-origin" });
    return ((await r.json()) as { token: string }).token;
  });
}

// ---------------------------------------------------------------- RFC 6238 (SHA-1, 6 digits, 30 s)
function base32Decode(s: string): Buffer {
  const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of s.toUpperCase().replace(/=+$/, "").replace(/\s/g, "")) bits += A.indexOf(c).toString(2).padStart(5, "0");
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}
/** `stepOffset` +1 gives the next period's code (the backend accepts +-1 and refuses a step it already used). */
export function totp(secret: string, stepOffset = 0, nowMs = Date.now()): string {
  const counter = BigInt(Math.floor(nowMs / 30_000) + stepOffset);
  const msg = Buffer.alloc(8);
  msg.writeBigUInt64BE(counter);
  const h = createHmac("sha1", base32Decode(secret)).update(msg).digest();
  const o = h[h.length - 1] & 0x0f;
  const n = ((h[o] & 0x7f) << 24) | (h[o + 1] << 16) | (h[o + 2] << 8) | h[o + 3];
  return String(n % 1_000_000).padStart(6, "0");
}

// ---------------------------------------------------------------- tiny valid fixtures, generated in memory
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);
export const pngFile = (name: string) => ({ name, mimeType: "image/png", buffer: PNG_1x1 });
export function pdfFile(name: string, text = "Setu e2e sample document") {
  const body = `BT /F1 12 Tf 20 100 Td (${text}) Tj ET`;
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${body.length} >>\nstream\n${body}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return { name, mimeType: "application/pdf", buffer: Buffer.from(out, "latin1") };
}

// ---------------------------------------------------------------- business identifiers
const USCC_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY";
const USCC_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28];
/** 18-char USCC with a valid GB 32100-2015 check character. */
export function validUscc(): string {
  const body = "91" + [...randomBytes(15)].map((b) => USCC_ALPHABET[b % 31]).join("");
  const sum = [...body].reduce((acc, c, i) => acc + USCC_WEIGHTS[i] * USCC_ALPHABET.indexOf(c), 0);
  return body + USCC_ALPHABET[(31 - (sum % 31)) % 31];
}
/** Same body, wrong check character. */
export function badChecksumUscc(): string {
  const good = validUscc();
  const wrong = USCC_ALPHABET[(USCC_ALPHABET.indexOf(good[17]) + 1) % 31];
  return good.slice(0, 17) + wrong;
}
export const randomDigits = (n: number) => [...randomBytes(n)].map((b) => b % 10).join("");
export const futureDate = (years = 2) => {
  const d = new Date();
  d.setUTCFullYear(d.getUTCFullYear() + years);
  return d.toISOString().slice(0, 10);
};
/** Valid-looking BD mobile (01[3-9] + 8 digits). */
export const bdMobile = () => `01${3 + (randomBytes(1)[0] % 7)}${randomDigits(8)}`;

// ---------------------------------------------------------------- field helpers
export const field = (page: Page, key: string) => page.locator(`#ob-${key.replace(/\./g, "_")}`);
export async function fill(page: Page, values: Record<string, string>) {
  for (const [k, v] of Object.entries(values)) await field(page, k).fill(v);
}
export async function expectStep(page: Page, n: number, total: number, name: string, lang: Lang = "en") {
  await expect(page.getByRole("heading", { level: 2, name: tr("ob.stepOf", lang, { n, total, name }) })).toBeVisible();
}
