import type { BankAccountInput, OnboardingInput } from "@/lib/api/onboarding";

export type Draft = {
  accountType: "BUYER" | "SUPPLIER" | "";
  displayName: string;
  legalName: string;
  licenseName: string;
  licenseNo: string;
  taxId: string;
  city: string;
  country: string;
  language: "en" | "bn" | "zh";
  bankName: string;
  bankCountry: string;
  accountNumber: string;
  holderName: string;
  currency: BankAccountInput["currency"];
  bankAccountType: BankAccountInput["account_type"];
};

export type FieldKey = Exclude<keyof Draft, "language">;
export type FieldError = { key: string; vars?: Record<string, string | number> };
export type Errors = Partial<Record<FieldKey, FieldError>>;

export const EMPTY_DRAFT: Draft = {
  accountType: "",
  displayName: "",
  legalName: "",
  licenseName: "",
  licenseNo: "",
  taxId: "",
  city: "",
  country: "BD",
  language: "en",
  bankName: "",
  bankCountry: "BD",
  accountNumber: "",
  holderName: "",
  currency: "BDT",
  bankAccountType: "CORPORATE",
};

/** Which wizard step each field lives on (0 type, 1 company, 2 bank). */
export const FIELD_STEP: Record<FieldKey, number> = {
  accountType: 0,
  displayName: 0,
  legalName: 1,
  licenseName: 1,
  licenseNo: 1,
  taxId: 1,
  city: 1,
  country: 1,
  bankName: 2,
  bankCountry: 2,
  accountNumber: 2,
  holderName: 2,
  currency: 2,
  bankAccountType: 2,
};

/** Server field path (OnboardingIn) -> draft field. */
export const SERVER_FIELD: Record<string, FieldKey> = {
  account_type: "accountType",
  display_name: "displayName",
  legal_name: "legalName",
  license_name: "licenseName",
  license_no: "licenseNo",
  tax_id: "taxId",
  city: "city",
  country: "country",
  "bank_account.bank_name": "bankName",
  "bank_account.bank_country": "bankCountry",
  "bank_account.account_number": "accountNumber",
  "bank_account.holder_name": "holderName",
  "bank_account.currency": "currency",
  "bank_account.account_type": "bankAccountType",
};

const ISO2 = /^[A-Za-z]{2}$/;
const ACCOUNT_NO = /^[A-Za-z0-9]{8,34}$/;
const BD_TIN = /^\d{9,13}$/;

function len(value: string, min: number, max: number): FieldError | undefined {
  const v = value.trim();
  if (v.length === 0) return { key: "onb.v.required" };
  if (v.length < min || v.length > max) return { key: "onb.v.length", vars: { min, max } };
  return undefined;
}

/** Mirrors the backend rules (backend/app/schemas/onboarding.py) so most mistakes are caught before the request. */
export function validateStep(step: number, d: Draft): Errors {
  const e: Errors = {};
  const set = (k: FieldKey, v: FieldError | undefined) => {
    if (v) e[k] = v;
  };
  if (step === 0) {
    if (!d.accountType) e.accountType = { key: "onb.v.required" };
    set("displayName", len(d.displayName, 2, 120));
  } else if (step === 1) {
    set("legalName", len(d.legalName, 2, 200));
    if (d.licenseName.trim()) set("licenseName", len(d.licenseName, 2, 200));
    set("licenseNo", len(d.licenseNo, 3, 64));
    set("taxId", len(d.taxId, 5, 32));
    if (!e.taxId && d.accountType === "BUYER" && d.country === "BD" && !BD_TIN.test(d.taxId.trim())) {
      e.taxId = { key: "onb.v.tin" };
    }
    set("city", len(d.city, 2, 80));
    if (!ISO2.test(d.country.trim())) e.country = { key: "onb.v.iso2" };
  } else if (step === 2) {
    set("bankName", len(d.bankName, 2, 120));
    if (!ISO2.test(d.bankCountry.trim())) e.bankCountry = { key: "onb.v.iso2" };
    const n = d.accountNumber.trim();
    if (!n) e.accountNumber = { key: "onb.v.required" };
    else if (n.toUpperCase().startsWith("SIM-")) e.accountNumber = { key: "onb.v.simAccount" };
    else if (!ACCOUNT_NO.test(n)) e.accountNumber = { key: "onb.v.account" };
    set("holderName", len(d.holderName, 2, 200));
  }
  return e;
}

export function toInput(d: Draft): OnboardingInput {
  if (!d.accountType) throw new Error("account type is required");
  return {
    account_type: d.accountType,
    display_name: d.displayName.trim(),
    legal_name: d.legalName.trim(),
    license_name: d.licenseName.trim() || null,
    license_no: d.licenseNo.trim(),
    tax_id: d.taxId.trim(),
    city: d.city.trim(),
    country: d.country.trim().toUpperCase(),
    language: d.language,
    bank_account: {
      bank_name: d.bankName.trim(),
      bank_country: d.bankCountry.trim().toUpperCase(),
      account_number: d.accountNumber.trim(),
      holder_name: d.holderName.trim(),
      currency: d.currency,
      account_type: d.bankAccountType,
    },
  };
}
