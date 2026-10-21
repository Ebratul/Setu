// Regenerates the documentation screenshots: node scripts/docs-screenshots.mjs [--base URL] [--lang en,bn] [--only buyer/deals-new]
// Needs the web app + API running against a LOCAL demo database (`make dev`, seeded). For each <Screenshot name route as .../>
// in content/docs it signs in as that role's demo user, opens the route in the page's language and writes
// public/docs-images/<lang>/<name>.png. Pages that fail are listed at the end (exit code 1) so stale images are never silent.
import { mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const content = path.join(root, "content", "docs");
const out = path.join(root, "public", "docs-images");

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : fallback;
};
const base = arg("base", process.env.E2E_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
const langs = arg("lang", "en,bn,zh").split(",");
const only = arg("only", "");

const USERS = {
  buyer: "rahima@demo.setu",
  supplier: "huaxin@demo.setu",
  admin: "admin@demo.setu",
  judge: "judge@demo.setu",
};

function attrs(tag) {
  const o = {};
  for (const m of tag.matchAll(/(\w+)="([^"]*)"/g)) o[m[1]] = m[2];
  return o;
}

function collect() {
  const shots = new Map();
  for (const lang of langs) {
    const dir = path.join(content, lang);
    for (const section of safeDir(dir)) {
      for (const file of readdirSync(path.join(dir, section))) {
        if (!file.endsWith(".mdx")) continue;
        const body = readFileSync(path.join(dir, section, file), "utf8");
        for (const m of body.matchAll(/<Screenshot\b([\s\S]*?)\/>/g)) {
          const a = attrs(m[1]);
          if (!a.name || !a.route || (only && a.name !== only)) continue;
          shots.set(`${lang}:${a.name}`, { lang, ...a });
        }
      }
    }
  }
  return [...shots.values()];
}

function safeDir(dir) {
  try {
    return readdirSync(dir).filter((n) => statSync(path.join(dir, n)).isDirectory());
  } catch {
    return [];
  }
}

const shots = collect();
if (shots.length === 0) {
  console.log("No <Screenshot> tags found.");
  process.exit(0);
}

const browser = await chromium.launch();
const failures = [];
const contexts = new Map();

async function pageFor(role, lang) {
  const key = `${role}:${lang}`;
  if (!contexts.has(key)) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, baseURL: base, locale: lang === "zh" ? "zh-CN" : lang === "bn" ? "bn-BD" : "en-US" });
    await ctx.addCookies([{ name: "setu_lang", value: lang, url: base }]);
    const res = await ctx.request.post("/api/auth/demo-login", { data: { email: USERS[role] ?? USERS.buyer } });
    if (!res.ok()) throw new Error(`demo-login ${role} failed: ${res.status()}`);
    contexts.set(key, ctx);
  }
  return contexts.get(key).newPage();
}

for (const s of shots) {
  const label = `${s.lang}/${s.name}`;
  try {
    const page = await pageFor(s.as ?? "buyer", s.lang);
    await page.goto(s.route, { waitUntil: "networkidle" });
    if (s.wait) await page.locator(s.wait).first().waitFor({ timeout: 10_000 });
    if (s.click) await page.locator(s.click).first().click({ timeout: 10_000 });
    await page.waitForTimeout(400);
    const file = path.join(out, s.lang, `${s.name}.png`);
    mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file });
    await page.close();
    console.log(`ok   ${label}`);
  } catch (e) {
    failures.push(`${label}: ${String(e.message).split("\n")[0]}`);
    console.log(`FAIL ${label}`);
  }
}

await browser.close();
if (failures.length) {
  console.error(`\n${failures.length} screenshot(s) failed:\n${failures.join("\n")}`);
  process.exit(1);
}
