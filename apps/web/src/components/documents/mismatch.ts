import type { FindingOut } from "@/lib/api/documents";

export type Mismatch = {
  /** field key as used in `fields` */
  field: string;
  /** the conflicting value from the other document / the deal */
  expected: string;
  /** a doc type, "deal", or null when unknown */
  against: string | null;
  check: string;
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown): string | null =>
  typeof v === "string" || typeof v === "number" ? String(v) : null;

const PARTY_FIELDS = ["seller", "shipper", "exporter", "supplier"];
const BENEFICIARY_FIELDS: Record<string, string> = {
  holder: "bank_holder",
  bank: "bank_name",
  account: "bank_account",
};

/** Conflicting values named in FAIL/WARN findings, keyed by extracted field. Pure; no document text is interpreted. */
export function mismatchesFromFindings(
  findings: readonly FindingOut[],
  fields: Record<string, unknown> | null,
): Mismatch[] {
  const out: Mismatch[] = [];
  const add = (m: Mismatch) => {
    if (!out.some((x) => x.field === m.field && x.expected === m.expected)) out.push(m);
  };
  for (const f of findings) {
    if (f.status !== "FAIL" && f.status !== "WARN") continue;
    const d = f.detail;
    if (Array.isArray(d.conflicts)) {
      for (const c of d.conflicts) {
        if (!isObj(c)) continue;
        const field = text(c.field);
        const expected = text(c.expected);
        if (field && expected !== null) {
          add({ field, expected, against: text(c.against), check: f.check_code });
        }
      }
    }
    if (f.check_code === "NAME_MATCH") {
      const expected = text(d.expected);
      const found = text(d.found);
      const field = PARTY_FIELDS.find((k) => fields && text(fields[k]) === found) ?? PARTY_FIELDS.find((k) => fields && k in fields);
      if (field && expected) add({ field, expected, against: "deal", check: f.check_code });
    }
    if (f.check_code === "BENEFICIARY_MATCH") {
      for (const [k, field] of Object.entries(BENEFICIARY_FIELDS)) {
        const part = d[k];
        if (isObj(part) && text(part.expected)) {
          add({ field, expected: text(part.expected) as string, against: "deal", check: f.check_code });
        }
      }
    }
    if (f.check_code === "VALUE_MATH") {
      const computed = text(d.computed);
      if (computed) add({ field: "total", expected: computed, against: null, check: f.check_code });
    }
  }
  return out;
}

export function fieldLabel(key: string): string {
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

/** Plain string for any extracted value; never HTML. */
export function fieldValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}
