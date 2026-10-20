import { describe, expect, it } from "vitest";

import { fieldErrors } from "@/lib/api/formErrors";
import { ApiError } from "@/lib/api/client";

import { EMPTY_DRAFT, toInput, validateStep, type Draft } from "./validate";

const base: Draft = {
  ...EMPTY_DRAFT,
  accountType: "BUYER",
  displayName: "Rahim",
  legalName: "Rahim Ltd",
  licenseNo: "TL-1",
  taxId: "123456789",
  city: "Dhaka",
  bankName: "Bank",
  accountNumber: "12345678",
  holderName: "Rahim Ltd",
};

describe("validateStep", () => {
  it("accepts a complete draft", () => {
    for (const s of [0, 1, 2]) expect(validateStep(s, base)).toEqual({});
  });
  it("applies the BD buyer TIN rule only to BD buyers", () => {
    expect(validateStep(1, { ...base, taxId: "ABC12" }).taxId?.key).toBe("onb.v.tin");
    expect(validateStep(1, { ...base, taxId: "ABC12", accountType: "SUPPLIER" }).taxId).toBeUndefined();
    expect(validateStep(1, { ...base, taxId: "ABC12", country: "CN" }).taxId).toBeUndefined();
  });
  it("checks account number shape", () => {
    expect(validateStep(2, { ...base, accountNumber: "short" }).accountNumber?.key).toBe("onb.v.account");
    expect(validateStep(2, { ...base, accountNumber: "SIM-12345678" }).accountNumber?.key).toBe("onb.v.simAccount");
  });
  it("builds the request body", () => {
    const body = toInput({ ...base, country: "bd", bankCountry: "bd" });
    expect(body.country).toBe("BD");
    expect(body.license_name).toBeNull();
    expect(body.bank_account.bank_country).toBe("BD");
  });
});

describe("fieldErrors", () => {
  it("maps a FastAPI 422 body to field paths and ignores other errors", () => {
    const detail = JSON.stringify([{ loc: ["body", "bank_account", "account_number"], msg: "bad" }]);
    expect(fieldErrors(new ApiError(422, "x", detail))).toEqual({ "bank_account.account_number": "bad" });
    expect(fieldErrors(new ApiError(409, "x", detail))).toEqual({});
    expect(fieldErrors(new ApiError(422, "x", "plain"))).toEqual({});
  });
});
