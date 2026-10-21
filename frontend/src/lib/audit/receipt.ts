import type { AuditLine } from "./verify";

const SIGNED_FIELDS = [
  "seq",
  "ts",
  "actor_type",
  "actor_id",
  "deal_id",
  "action",
  "tier",
  "decision",
  "payload",
  "payload_hash",
  "prev_hash",
  "entry_hash",
  "signature",
  "key_id",
] as const;

export const RECEIPT_ACTIONS = [
  "TRANCHE_RELEASED",
  "MILESTONE_RELEASED",
  "APPROVAL_APPROVED",
  "APPROVAL_EXECUTED",
] as const;

export const isReceiptAction = (action: string) => (RECEIPT_ACTIONS as readonly string[]).includes(action);

export function b64urlEncode(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function b64urlDecode(s: string): string {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

/** Only the signed fields travel in the receipt (no display text, no secrets). */
export function signedEntry(entry: AuditLine): AuditLine {
  const out: Record<string, unknown> = {};
  for (const k of SIGNED_FIELDS) out[k] = entry[k];
  return out as AuditLine;
}

export function receiptUrl(entry: AuditLine, origin: string): string {
  const q = new URLSearchParams({ seq: String(entry.seq), hash: entry.entry_hash });
  return `${origin}/verify?${q}#e=${b64urlEncode(JSON.stringify(signedEntry(entry)))}`;
}

export type ReceiptParams = { seq: number | null; hash: string | null; entry: unknown };

/** Reads `?seq=&hash=` and `#e=` from a location-like URL; entry is null when absent or unreadable. */
export function parseReceiptUrl(href: string): ReceiptParams {
  const url = new URL(href, "http://localhost");
  const seqRaw = url.searchParams.get("seq");
  const seq = seqRaw && /^\d+$/.test(seqRaw) ? Number(seqRaw) : null;
  const hash = url.searchParams.get("hash");
  const m = /(?:^#|&)e=([A-Za-z0-9_-]+)/.exec(url.hash);
  let entry: unknown = null;
  if (m) {
    try {
      entry = JSON.parse(b64urlDecode(m[1]));
    } catch {
      entry = null;
    }
  }
  return { seq, hash, entry };
}
