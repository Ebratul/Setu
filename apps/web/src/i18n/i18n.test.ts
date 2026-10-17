import { describe, expect, it } from "vitest";

import { messages, translate } from "./index";

describe("i18n dictionaries", () => {
  it("keeps en and bn in parity", () => {
    expect(Object.keys(messages.bn).sort()).toEqual(Object.keys(messages.en).sort());
  });

  it("zh only holds keys that also exist in en (it falls back to en)", () => {
    const stray = Object.keys(messages.zh).filter((k) => !(k in messages.en));
    expect(stray).toEqual([]);
  });

  it("has every supplier-portal key in en, bn and zh", () => {
    const sp = Object.keys(messages.en).filter((k) => k.startsWith("sp."));
    expect(sp.length).toBeGreaterThan(10);
    for (const k of sp) {
      expect(messages.bn[k], k).toBeTruthy();
      expect(messages.zh[k], k).toBeTruthy();
    }
  });

  it("keeps placeholders identical across languages", () => {
    const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    for (const [k, v] of Object.entries(messages.zh)) {
      expect(vars(v), k).toBe(vars(messages.en[k]));
    }
    for (const [k, v] of Object.entries(messages.bn)) {
      expect(vars(v), k).toBe(vars(messages.en[k]));
    }
  });

  it("falls back to en for untranslated zh keys", () => {
    expect(translate("zh", "deals.title")).toBe("Deals");
    expect(translate("zh", "sp.orders")).toBe("订单");
  });
});
