// Fails (exit 1) when a UI key is missing in Bangla, or in Chinese for the supplier / landing scopes.
// Run: pnpm --dir frontend i18n:check   (wired into `make lint`)
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../src/i18n/", import.meta.url).pathname;
const ZH_SCOPES = ["landing.", "a11y.", "notfound.", "errpage.", "sp.", "chg.", "common.", "lang.", "ui."];

function flatten(obj, prefix = "", out = {}) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else flatten(v, key, out);
  }
  return out;
}

function load(lang) {
  const files = [`${lang}.json`, ...readdirSync(join(dir, "parts")).filter((f) => f.endsWith(`.${lang}.json`)).map((f) => `parts/${f}`)];
  return Object.assign({}, ...files.map((f) => flatten(JSON.parse(readFileSync(join(dir, f), "utf8")))));
}

const en = load("en");
const bn = load("bn");
const zh = load("zh");
const problems = [];
const placeholders = (s) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");

for (const key of Object.keys(en)) {
  if (!(key in bn) || bn[key].trim() === "") problems.push(`bn missing: ${key}`);
  else if (placeholders(bn[key]) !== placeholders(en[key])) problems.push(`bn placeholder mismatch: ${key}`);
  if (ZH_SCOPES.some((s) => key.startsWith(s))) {
    if (!(key in zh) || zh[key].trim() === "") problems.push(`zh missing: ${key}`);
    else if (placeholders(zh[key]) !== placeholders(en[key])) problems.push(`zh placeholder mismatch: ${key}`);
  }
}
for (const key of Object.keys(bn)) if (!(key in en)) problems.push(`bn orphan (not in en): ${key}`);

if (problems.length) {
  console.error(`i18n check failed (${problems.length}):\n${problems.slice(0, 80).join("\n")}`);
  process.exit(1);
}
console.log(`i18n ok: ${Object.keys(en).length} en keys; bn complete; zh complete for ${ZH_SCOPES.join(" ")}`);
