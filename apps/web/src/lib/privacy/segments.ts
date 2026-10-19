import type { PrivacyType, Segment } from "./types";

export type TypeMeta = {
  icon: string;
  code: string;
  /** Static class strings so Tailwind can see them. */
  mark: string;
  swatch: string;
};

export const TYPE_ORDER: readonly PrivacyType[] = [
  "NID",
  "PASSPORT",
  "PHONE",
  "ACCT",
  "IBAN",
  "SWIFT",
  "EMAIL",
  "NAME",
  "AMT",
];

const base = "rounded-sm border-b-2 px-0.5 text-ink";

export const TYPE_META: Record<PrivacyType, TypeMeta> = {
  NID: { icon: "🪪", code: "NID", mark: `${base} border-chart-4 bg-chart-4/15`, swatch: "bg-chart-4" },
  PASSPORT: { icon: "🛂", code: "PP", mark: `${base} border-chart-5 bg-chart-5/15`, swatch: "bg-chart-5" },
  PHONE: { icon: "☎", code: "TEL", mark: `${base} border-info bg-info/15`, swatch: "bg-info" },
  ACCT: { icon: "#", code: "ACCT", mark: `${base} border-chart-1 bg-chart-1/15`, swatch: "bg-chart-1" },
  IBAN: { icon: "⌗", code: "IBAN", mark: `${base} border-success bg-success/15`, swatch: "bg-success" },
  SWIFT: { icon: "⇄", code: "SWIFT", mark: `${base} border-chart-6 bg-chart-6/15`, swatch: "bg-chart-6" },
  EMAIL: { icon: "@", code: "MAIL", mark: `${base} border-chart-2 bg-chart-2/15`, swatch: "bg-chart-2" },
  NAME: { icon: "☺", code: "NAME", mark: `${base} border-warning bg-warning/15`, swatch: "bg-warning" },
  AMT: { icon: "৳", code: "AMT", mark: `${base} border-danger bg-danger/15`, swatch: "bg-danger" },
};

const FALLBACK: TypeMeta = {
  icon: "•",
  code: "?",
  mark: `${base} border-muted bg-muted/15`,
  swatch: "bg-muted",
};

export function isPrivacyType(v: string | null | undefined): v is PrivacyType {
  return v !== null && v !== undefined && v in TYPE_META;
}

export function typeMeta(type: string | null | undefined): TypeMeta {
  return isPrivacyType(type) ? TYPE_META[type] : FALLBACK;
}

/** Non-empty counts ordered by the canonical type order, unknown types last. */
export function orderedCounts(byType: Record<string, number>): [string, number][] {
  const rank = (k: string) => {
    const i = TYPE_ORDER.indexOf(k as PrivacyType);
    return i === -1 ? TYPE_ORDER.length : i;
  };
  return Object.entries(byType)
    .filter(([, n]) => n > 0)
    .sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]));
}

export const segmentsToText = (segs: readonly Segment[]) => segs.map((s) => s.text).join("");

export const protectedCount = (segs: readonly Segment[]) => segs.filter((s) => s.type !== null).length;

const TOKEN_RE = /⟦([A-Z]+)_\d+⟧/g;

/** Splits a masked string into plain and token segments (for display of stored masked payloads). */
export function tokenize(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(TOKEN_RE)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ text: text.slice(last, at), type: null, token: null });
    out.push({ text: m[0], type: m[1], token: m[0] });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), type: null, token: null });
  return out;
}
