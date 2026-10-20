/**
 * Browser verifier for audit scheme `setu-audit-v2`. Mirrors services/agent/app/audit/{scheme,verify}.py.
 * Pure: no network, no DOM. Ed25519 comes from Web Crypto, with @noble/ed25519 as the fallback.
 */

export const SCHEME = "setu-audit-v2";
export const GENESIS_HASH = "0".repeat(64);

const BODY_FIELDS = [
  "seq",
  "ts",
  "actor_type",
  "actor_id",
  "deal_id",
  "action",
  "tier",
  "decision",
  "payload",
] as const;
const LINE_FIELDS = [
  ...BODY_FIELDS,
  "payload_hash",
  "prev_hash",
  "entry_hash",
  "signature",
  "key_id",
] as const;

export type AuditLine = {
  seq: number;
  ts: string;
  actor_type: string;
  actor_id: string;
  deal_id: string | null;
  action: string;
  tier: number;
  decision: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  entry_hash: string;
  signature: string;
  key_id: string;
};

export type FailReason =
  | "hash_mismatch"
  | "bad_signature"
  | "missing_seq"
  | "reordered"
  | "broken_link"
  | "malformed";

export type VerifyReport = {
  ok: boolean;
  entriesChecked: number;
  firstSeq: number | null;
  lastSeq: number | null;
  brokenSeq: number | null;
  reason: FailReason | null;
  detail: string | null;
  anchored: boolean;
  contiguous: boolean;
  missingSeqs: number;
};

export type ExportHeader = Record<string, unknown> & { contiguous?: boolean };

export class AuditParseError extends Error {
  readonly line: number | null;
  constructor(message: string, line: number | null = null) {
    super(message);
    this.name = "AuditParseError";
    this.line = line;
  }
}

function cmpCodePoints(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = (x[i].codePointAt(0) ?? 0) - (y[i].codePointAt(0) ?? 0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

/** Sorted keys, no whitespace, strings as JSON.stringify writes them. Floats are refused, as in Python. */
export function canonicalJson(value: unknown): string {
  if (value === null) return "null";
  switch (typeof value) {
    case "string":
      return JSON.stringify(value);
    case "boolean":
      return value ? "true" : "false";
    case "number":
      if (!Number.isInteger(value))
        throw new TypeError("floats are not allowed in audit payloads");
      return String(value);
    case "object": {
      if (Array.isArray(value))
        return `[${value.map(canonicalJson).join(",")}]`;
      const obj = value as Record<string, unknown>;
      const keys = Object.keys(obj).sort(cmpCodePoints);
      return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`).join(",")}}`;
    }
    default:
      throw new TypeError(`not canonicalisable: ${typeof value}`);
  }
}

const hex = (bytes: Uint8Array) =>
  Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");

function fromHex(s: string): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++)
    out[i] = parseInt(s.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return hex(new Uint8Array(digest));
}

export function bodyOf(line: AuditLine): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const k of BODY_FIELDS) body[k] = line[k];
  return body;
}

export const computePayloadHash = (line: AuditLine) =>
  sha256Hex(canonicalJson(bodyOf(line)));

export const computeEntryHash = (
  prev: string,
  payloadHash: string,
  seq: number,
  ts: string,
) => sha256Hex(`${prev}|${payloadHash}|${seq}|${ts}`);

/** Raw 32-byte key from an SPKI PEM (the last 32 bytes of the DER). */
export function parsePublicKeyPem(pem: string): Uint8Array<ArrayBuffer> {
  const m = /-----BEGIN PUBLIC KEY-----([\s\S]+?)-----END PUBLIC KEY-----/.exec(
    pem,
  );
  if (!m) throw new AuditParseError("not a PEM public key");
  let der: string;
  try {
    der = atob(m[1].replace(/\s+/g, ""));
  } catch {
    throw new AuditParseError("the PEM body is not valid base64");
  }
  if (der.length < 32) throw new AuditParseError("the public key is too short");
  return Uint8Array.from(der.slice(-32), (c) => c.charCodeAt(0));
}

export async function fingerprint(
  rawKey: Uint8Array<ArrayBuffer>,
): Promise<string> {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", rawKey)));
}

async function verifySignature(
  rawKey: Uint8Array<ArrayBuffer>,
  entryHash: string,
  signature: string,
): Promise<boolean> {
  const message = fromHex(entryHash);
  const sig = fromHex(signature);
  try {
    const key = await crypto.subtle.importKey(
      "raw",
      rawKey,
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify({ name: "Ed25519" }, key, sig, message);
  } catch {
    try {
      const ed = await import("@noble/ed25519");
      return await ed.verifyAsync(sig, message, rawKey);
    } catch {
      return false;
    }
  }
}

function isHex(v: unknown, n: number): boolean {
  return typeof v === "string" && v.length === n && /^[0-9a-f]+$/.test(v);
}

function wellFormed(line: Record<string, unknown>): string | null {
  const missing = LINE_FIELDS.filter((f) => !(f in line));
  if (missing.length) return `missing field ${missing[0]}`;
  if (typeof line.seq !== "number" || !Number.isInteger(line.seq))
    return "seq is not an integer";
  const p = line.payload;
  if (
    typeof line.ts !== "string" ||
    p === null ||
    typeof p !== "object" ||
    Array.isArray(p)
  ) {
    return "ts or payload has the wrong type";
  }
  for (const f of ["payload_hash", "prev_hash", "entry_hash"]) {
    if (!isHex(line[f], 64)) return `${f} is not a sha256 hex digest`;
  }
  if (!isHex(line.signature, 128)) return "signature is not 64 bytes of hex";
  return null;
}

export type VerifyOptions = {
  contiguous?: boolean;
  anchorPrevHash?: string | null;
};

/** Same rules, order and reasons as verify_lines() in verify.py. */
export async function verifyLines(
  input: readonly unknown[],
  rawKey: Uint8Array<ArrayBuffer>,
  opts: VerifyOptions = {},
): Promise<VerifyReport> {
  const contiguous = opts.contiguous ?? true;
  const raw = input as Record<string, unknown>[];
  const seqOf = (l: Record<string, unknown> | undefined) =>
    typeof l?.seq === "number" ? l.seq : null;
  const report: VerifyReport = {
    ok: true,
    entriesChecked: 0,
    firstSeq: raw.length ? seqOf(raw[0]) : null,
    lastSeq: raw.length ? seqOf(raw[raw.length - 1]) : null,
    brokenSeq: null,
    reason: null,
    detail: null,
    anchored: false,
    contiguous,
    missingSeqs: 0,
  };
  const fail = (
    seq: number | null,
    reason: FailReason,
    detail: string,
  ): VerifyReport => {
    report.ok = false;
    report.brokenSeq = seq;
    report.reason = reason;
    report.detail = detail;
    return report;
  };

  let prev: AuditLine | null = null;
  const later = new Set(raw.map(seqOf));
  for (let index = 0; index < raw.length; index++) {
    const rec = raw[index];
    const bad =
      rec === null || typeof rec !== "object"
        ? "entry is not an object"
        : wellFormed(rec);
    if (bad) return fail(seqOf(rec), "malformed", bad);
    const line = rec as unknown as AuditLine;
    const seq = line.seq;
    if (prev !== null) {
      const expected = prev.seq + 1;
      if (contiguous && seq !== expected) {
        if (later.has(expected))
          return fail(
            expected,
            "reordered",
            `seq ${seq} appears where seq ${expected} belongs`,
          );
        return fail(
          expected,
          "missing_seq",
          `seq ${expected} is missing (found ${seq})`,
        );
      }
      if (seq <= prev.seq)
        return fail(seq, "reordered", `seq ${seq} follows seq ${prev.seq}`);
    }
    let payloadHash: string;
    try {
      payloadHash = await computePayloadHash(line);
    } catch (e) {
      return fail(
        seq,
        "malformed",
        e instanceof Error ? e.message : "cannot canonicalise entry",
      );
    }
    if (payloadHash !== line.payload_hash) {
      return fail(
        seq,
        "hash_mismatch",
        "payload_hash does not match the entry contents",
      );
    }
    if (
      (await computeEntryHash(
        line.prev_hash,
        line.payload_hash,
        seq,
        line.ts,
      )) !== line.entry_hash
    ) {
      return fail(
        seq,
        "hash_mismatch",
        "entry_hash does not match prev_hash, payload, seq, ts",
      );
    }
    if (!(await verifySignature(rawKey, line.entry_hash, line.signature))) {
      return fail(
        seq,
        "bad_signature",
        "Ed25519 signature does not verify against the key",
      );
    }
    if (
      prev !== null &&
      seq === prev.seq + 1 &&
      line.prev_hash !== prev.entry_hash
    ) {
      return fail(
        seq,
        "broken_link",
        `prev_hash does not equal entry_hash of seq ${seq - 1}`,
      );
    }
    if (index === 0) {
      if (seq === 1) {
        if (line.prev_hash !== GENESIS_HASH)
          return fail(
            seq,
            "broken_link",
            "seq 1 must link to the genesis hash",
          );
        report.anchored = true;
      } else if (
        opts.anchorPrevHash != null &&
        line.prev_hash !== opts.anchorPrevHash
      ) {
        return fail(
          seq,
          "broken_link",
          `prev_hash does not equal entry_hash of seq ${seq - 1}`,
        );
      }
    }
    prev = line;
    report.entriesChecked += 1;
  }
  if (!contiguous) {
    report.anchored = false;
    if (report.entriesChecked > 0) {
      report.missingSeqs = Number(raw[raw.length - 1].seq) - Number(raw[0].seq) + 1 - report.entriesChecked;
    }
  }
  return report;
}

/** One entry on its own: hash and signature only. It cannot prove chain continuity. */
export function verifySingle(
  line: unknown,
  rawKey: Uint8Array<ArrayBuffer>,
): Promise<VerifyReport> {
  return verifyLines([line], rawKey, { contiguous: false });
}

/** JSONL export: an optional header line (has `scheme`, no `seq`), then one entry per line. */
export function parseExport(text: string): {
  header: ExportHeader | null;
  entries: AuditLine[];
} {
  let header: ExportHeader | null = null;
  const entries: AuditLine[] = [];
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    let obj: unknown;
    try {
      obj = JSON.parse(lines[i]);
    } catch {
      throw new AuditParseError(`line ${i + 1} is not JSON`, i + 1);
    }
    if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
      throw new AuditParseError(`line ${i + 1} is not a JSON object`, i + 1);
    }
    const rec = obj as Record<string, unknown>;
    if (
      !("seq" in rec) &&
      "scheme" in rec &&
      header === null &&
      entries.length === 0
    )
      header = rec;
    else entries.push(rec as unknown as AuditLine);
  }
  return { header, entries };
}

/** Verify a whole export text with a PEM key. */
export async function verifyExport(
  text: string,
  pem: string,
): Promise<VerifyReport & { fingerprint: string }> {
  const key = parsePublicKeyPem(pem);
  const { header, entries } = parseExport(text);
  const contiguous = header ? header.contiguous !== false : true;
  const report = await verifyLines(entries, key, { contiguous });
  return { ...report, fingerprint: await fingerprint(key) };
}
