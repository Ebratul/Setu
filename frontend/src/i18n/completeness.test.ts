import { describe, expect, it } from "vitest";

import { messages } from "./index";

const ZH_SCOPES = ["landing.", "a11y.", "notfound.", "errpage.", "sp.", "chg.", "common.", "lang.", "ui."];
const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");

describe("i18n completeness", () => {
  it("has every English key in Bangla with the same placeholders", () => {
    const bad = Object.keys(messages.en).filter(
      (k) => !messages.bn[k]?.trim() || vars(messages.bn[k]) !== vars(messages.en[k]),
    );
    expect(bad).toEqual([]);
  });

  it("has Chinese for the supplier and landing scopes", () => {
    const bad = Object.keys(messages.en)
      .filter((k) => ZH_SCOPES.some((s) => k.startsWith(s)))
      .filter((k) => !messages.zh[k]?.trim() || vars(messages.zh[k]) !== vars(messages.en[k]));
    expect(bad).toEqual([]);
  });

  it("has no Bangla keys without an English source", () => {
    expect(Object.keys(messages.bn).filter((k) => !(k in messages.en))).toEqual([]);
  });
});
