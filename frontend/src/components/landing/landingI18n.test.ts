import { describe, expect, it } from "vitest";

import bn from "@/i18n/parts/landing.bn.json";
import en from "@/i18n/parts/landing.en.json";
import zh from "@/i18n/parts/landing.zh.json";

type Dict = { [k: string]: string | Dict };
const flat = (d: Dict, p = ""): string[] =>
  Object.entries(d).flatMap(([k, v]) => (typeof v === "string" ? [`${p}${k}`] : flat(v, `${p}${k}.`)));

describe("landing and a11y strings", () => {
  it("have identical keys in en, bn and zh", () => {
    const e = flat(en as Dict).sort();
    expect(flat(bn as Dict).sort()).toEqual(e);
    expect(flat(zh as Dict).sort()).toEqual(e);
    expect(e.length).toBeGreaterThan(150);
  });
});
