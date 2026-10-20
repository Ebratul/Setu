import { readFileSync } from "node:fs";
import path from "node:path";

import jsQR from "jsqr";
import QRCode from "qrcode";
import { describe, expect, it } from "vitest";

import { b64urlDecode, b64urlEncode, isReceiptAction, parseReceiptUrl, receiptUrl } from "./receipt";
import { parseExport, parsePublicKeyPem, verifySingle } from "./verify";

const FIX = path.resolve(import.meta.dirname, "../../../e2e/fixtures/audit");
const { entries } = parseExport(readFileSync(path.join(FIX, "good.jsonl"), "utf-8"));
const release = entries.find((e) => e.seq === 10)!;

describe("receipt helpers", () => {
  it("round-trips base64url with unicode", () => {
    const s = '{"a":"বাংলা ✓ ??>>"}';
    expect(b64urlDecode(b64urlEncode(s))).toBe(s);
    expect(b64urlEncode(s)).toMatch(/^[A-Za-z0-9_-]+$/);
  });

  it("receiptUrl carries seq, hash and the signed entry", async () => {
    const url = receiptUrl(release, "https://setu.example");
    expect(url.startsWith("https://setu.example/verify?seq=10&hash=")).toBe(true);
    const p = parseReceiptUrl(url);
    expect(p.seq).toBe(release.seq);
    expect(p.hash).toBe(release.entry_hash);
    expect((p.entry as typeof release).entry_hash).toBe(release.entry_hash);
    const key = parsePublicKeyPem(readFileSync(path.join(FIX, "test-public-key.pem"), "utf-8"));
    expect((await verifySingle(p.entry, key)).ok).toBe(true);
  });

  it("the QR code decodes back to the same URL", async () => {
    const url = receiptUrl(release, "https://setu.example");
    // jsqr cannot read the automatic v24 symbol this URL needs; v25 carries the same bytes.
    const qr = QRCode.create(url, { errorCorrectionLevel: "L", version: 25 });
    const n = qr.modules.size;
    const scale = 4;
    const margin = 4 * scale;
    const side = n * scale + margin * 2;
    const data = new Uint8ClampedArray(side * side * 4).fill(255);
    for (let y = 0; y < n; y++)
      for (let x = 0; x < n; x++) {
        if (!qr.modules.get(y, x)) continue;
        for (let dy = 0; dy < scale; dy++)
          for (let dx = 0; dx < scale; dx++) {
            const i = ((margin + y * scale + dy) * side + margin + x * scale + dx) * 4;
            data[i] = data[i + 1] = data[i + 2] = 0;
          }
      }
    const decoded = jsQR(data, side, side);
    expect(decoded?.data).toBe(url);
    const p = parseReceiptUrl(decoded!.data);
    expect(p.seq).toBe(release.seq);
    expect(p.hash).toBe(release.entry_hash);
  });

  it("knows which actions get a receipt", () => {
    expect(isReceiptAction("TRANCHE_RELEASED")).toBe(true);
    expect(isReceiptAction("DEAL_CREATED")).toBe(false);
  });
});
