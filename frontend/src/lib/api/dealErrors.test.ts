import { describe, expect, it } from "vitest";

import { translate } from "@/i18n";

import { ApiError } from "./client";
import { dealErrorKey, dealErrorText } from "./dealErrors";

const err = (code: string) => new ApiError(409, "x", "raw", code);
const CODES = [
  "COOLING_OFF",
  "OTP_REQUIRED",
  "OTP_INVALID",
  "OTP_LOCKED",
  "OTP_EXPIRED",
  "APPROVAL_EXPIRED",
  "APPROVAL_LOCKED",
  "BENEFICIARY_VIA_EMAIL",
  "EVIDENCE_NOT_VERIFIED",
];

describe("approval error codes", () => {
  it("maps every approval code to a specific key in English and Bengali", () => {
    for (const c of CODES) {
      expect(dealErrorKey(err(c))).toBe(`dealErr.${c}`);
      expect(translate("en", `dealErr.${c}`)).not.toBe(`dealErr.${c}`);
      expect(translate("bn", `dealErr.${c}`)).not.toBe(translate("en", `dealErr.${c}`));
    }
  });

  it("falls back to the generic message and appends detail only for unknown codes", () => {
    const t = (k: string) => translate("en", k);
    expect(dealErrorText(err("OTP_LOCKED"), t)).not.toContain("raw");
    expect(dealErrorText(err("SOMETHING_NEW"), t)).toContain("(raw)");
  });
});
