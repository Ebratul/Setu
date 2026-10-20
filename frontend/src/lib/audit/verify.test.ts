import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { canonicalJson, fingerprint, parseExport, parsePublicKeyPem, verifyExport, verifySingle } from "./verify";

const FIX = path.resolve(import.meta.dirname, "../../../e2e/fixtures/audit");
const read = (f: string) => readFileSync(path.join(FIX, f), "utf-8");
const pem = read("test-public-key.pem");
type Expected = { ok: boolean; broken_seq: number | null; reason: string | null; entries_checked: number };
const expected = JSON.parse(read("expected.json")) as Record<string, Expected | number>;

describe("browser verifier matches the Python CLI", () => {
  for (const name of ["good", "tampered-amount", "tampered-missing", "tampered-reordered"]) {
    it(name, async () => {
      const want = expected[name] as Expected;
      const got = await verifyExport(read(`${name}.jsonl`), pem);
      expect(got.ok).toBe(want.ok);
      expect(got.brokenSeq).toBe(want.broken_seq);
      expect(got.reason).toBe(want.reason);
      expect(got.entriesChecked).toBe(want.entries_checked);
    });
  }

  it("reports the header fingerprint of the key", async () => {
    const { header } = parseExport(read("good.jsonl"));
    expect(await fingerprint(parsePublicKeyPem(pem))).toBe(header?.public_key_fingerprint);
  });
});

describe("verifier details", () => {
  it("canonical JSON sorts keys, drops whitespace and keeps unicode", () => {
    expect(canonicalJson({ b: 1, a: ["x", null, true], c: "বাংলা" })).toBe('{"a":["x",null,true],"b":1,"c":"বাংলা"}');
  });

  it("refuses floats", () => {
    expect(() => canonicalJson({ a: 1.5 })).toThrow();
  });

  it("verifies a single entry and rejects a different key", async () => {
    const { entries } = parseExport(read("good.jsonl"));
    const key = parsePublicKeyPem(pem);
    expect((await verifySingle(entries[3], key)).ok).toBe(true);
    const other = Uint8Array.from(key);
    other[0] ^= 1;
    const bad = await verifySingle(entries[3], other);
    expect(bad.ok).toBe(false);
    expect(bad.reason).toBe("bad_signature");
  });

  it("flags a single entry whose contents changed", async () => {
    const { entries } = parseExport(read("good.jsonl"));
    const changed = { ...entries[9], payload: { ...entries[9].payload, amount: "1.00" } };
    expect((await verifySingle(changed, parsePublicKeyPem(pem))).reason).toBe("hash_mismatch");
  });

  it("reports malformed lines", async () => {
    expect(() => parseExport("{not json")).toThrow(/line 1/);
    const r = await verifyExport('{"seq":1}', pem);
    expect(r.reason).toBe("malformed");
  });

  it("ships the same production key as docs/submission", () => {
    const docs = path.resolve(import.meta.dirname, "../../../../docs/submission/audit-public-key.pem");
    const bundled = path.resolve(import.meta.dirname, "../../../public/audit-public-key.pem");
    expect(readFileSync(bundled, "utf-8")).toBe(readFileSync(docs, "utf-8"));
  });
});
