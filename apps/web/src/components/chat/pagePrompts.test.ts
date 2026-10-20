import { describe, expect, it } from "vitest";

import { messages } from "@/i18n";

import { promptKeysFor } from "./pagePrompts";

describe("promptKeysFor", () => {
  it.each([
    ["/app"],
    ["/app/cashflow"],
    ["/app/financing"],
    ["/app/analysis"],
    ["/app/deals/SETU-2026-0001"],
    ["/app/orders/abc/analysis"],
    ["/app/approvals"],
  ])("gives three translated prompts for %s", (path) => {
    const keys = promptKeysFor(path);
    expect(keys).toHaveLength(3);
    for (const k of keys ?? []) {
      expect(messages.en[k], `en:${k}`).toBeTruthy();
      expect(messages.bn[k], `bn:${k}`).toBeTruthy();
      // Pre-existing chat.suggest.* keys have no zh yet and fall back to English; new chatx keys must have zh.
      if (k.startsWith("chatx.")) expect(messages.zh[k], `zh:${k}`).toBeTruthy();
    }
  });
  it("falls back for other pages", () => {
    expect(promptKeysFor("/app/deals/new")).toBeNull();
    expect(promptKeysFor("/app/suppliers")).toBeNull();
    expect(promptKeysFor(null)).toBeNull();
  });
});
