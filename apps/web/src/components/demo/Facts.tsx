"use client";

import { hasKey, useLang, useT } from "@/i18n";
import { formatDate, formatMoney, formatPct, type Currency, type FormatLang } from "@/lib/format";

const MONEY: Record<string, Currency> = {
  landed_cost: "USD",
  shortfall: "USD",
  financed: "USD",
  total_cost: "USD",
  fx_saving_usd: "USD",
  released_usd: "USD",
  released_total: "USD",
  paid_cny: "CNY",
};
const PCT = new Set(["margin_pct"]);
const DATES = new Set(["shortfall_on", "registered_on"]);
const HIDDEN = new Set(["approval_id", "signals", "payload_hash", "fingerprint", "options", "split"]);
const DECIMAL = /^-?\d+(\.\d+)?$/;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export type Fact = { key: string; text: string };

/** Display-only formatting of the server's facts; nothing is computed. */
export function formatFacts(facts: Record<string, unknown> | undefined, lang: FormatLang): Fact[] {
  const out: Fact[] = [];
  for (const [key, v] of Object.entries(facts ?? {})) {
    if (HIDDEN.has(key) || v === null || v === undefined) continue;
    let text: string | null = null;
    if (typeof v === "string") {
      if (MONEY[key] && DECIMAL.test(v)) text = formatMoney(v, MONEY[key], lang);
      else if (PCT.has(key) && DECIMAL.test(v)) text = formatPct(v, lang);
      else if (DATES.has(key) && ISO_DAY.test(v)) text = formatDate(v, lang);
      else if (v.length <= 90) text = v;
    } else if (typeof v === "number") text = String(v);
    else if (typeof v === "boolean") text = v ? "✓" : "✗";
    else if (Array.isArray(v) && v.length <= 3 && v.every((x) => typeof x === "string")) text = v.join(", ");
    if (text !== null && text !== "") out.push({ key, text });
  }
  return out;
}

const humanize = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export function FactsList({ facts }: { facts: Record<string, unknown> | undefined }) {
  const t = useT();
  const { lang } = useLang();
  const items = formatFacts(facts, lang);
  if (items.length === 0) return null;
  return (
    <dl data-testid="facts" className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {items.map((f) => (
        <div key={f.key} className="rounded-xl border border-line bg-surface-alt p-2.5">
          <dt className="text-xs font-semibold text-muted">{hasKey(`demo.fact.${f.key}`) ? t(`demo.fact.${f.key}`) : humanize(f.key)}</dt>
          <dd className="text-base font-bold break-words text-ink" data-fact={f.key}>
            {f.text}
          </dd>
        </div>
      ))}
    </dl>
  );
}
