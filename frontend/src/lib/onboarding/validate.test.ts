import { describe, expect, it } from "vitest";

import {
  draftFromBusiness,
  isBdMobile,
  isFutureDate,
  isValidUscc,
  normalizeMobile,
  toBusinessBody,
  validateBusiness,
  validateContact,
  validateFile,
} from "./validate";

describe("USCC (GB 32100-2015)", () => {
  it("accepts codes with a correct check character", () => {
    expect(isValidUscc("91350100M000100Y43")).toBe(true);
    expect(isValidUscc("91110000100000000R")).toBe(true);
    expect(isValidUscc("9144030071526726XG")).toBe(true);
    expect(isValidUscc(" 91350100m000100y43 ")).toBe(true);
  });
  it("rejects a wrong check character, wrong length and letters outside the alphabet", () => {
    expect(isValidUscc("91350100M000100Y44")).toBe(false);
    expect(isValidUscc("91350100M000100Y4")).toBe(false);
    expect(isValidUscc("91350100M000100Y433")).toBe(false);
    expect(isValidUscc("91350100I000100Y43")).toBe(false);
    expect(isValidUscc("")).toBe(false);
  });
});

describe("Bangladesh mobile", () => {
  it("matches +8801[3-9]XXXXXXXX only", () => {
    expect(isBdMobile("+8801712345678")).toBe(true);
    expect(isBdMobile("+8801312345678")).toBe(true);
    expect(isBdMobile("+8801212345678")).toBe(false);
    expect(isBdMobile("+880171234567")).toBe(false);
    expect(isBdMobile("01712345678")).toBe(false);
  });
  it("normalises common local formats", () => {
    expect(normalizeMobile("01712345678")).toBe("+8801712345678");
    expect(normalizeMobile("8801712-345678")).toBe("+8801712345678");
    expect(normalizeMobile("+880 1712 345678")).toBe("+8801712345678");
  });
  it("validates the contact step by role", () => {
    const v = {
      full_name: "Rahim Uddin",
      designation: "Director",
      mobile: "01712345678",
    };
    expect(validateContact(v, "BUYER")).toEqual({});
    expect(
      validateContact({ ...v, mobile: "01212345678" }, "BUYER").mobile?.key,
    ).toBe("ob.v.mobile");
    expect(
      validateContact({ ...v, mobile: "+8613812345678" }, "SUPPLIER"),
    ).toEqual({});
    expect(
      validateContact({ ...v, full_name: "" }, "BUYER").full_name?.key,
    ).toBe("ob.v.required");
  });
});

describe("dates and files", () => {
  const now = new Date("2026-10-20T10:00:00Z");
  it("requires a real future date", () => {
    expect(isFutureDate("2026-10-21", now)).toBe(true);
    expect(isFutureDate("2026-10-20", now)).toBe(false);
    expect(isFutureDate("2026-02-31", now)).toBe(false);
    expect(isFutureDate("tomorrow", now)).toBe(false);
  });
  it("limits upload type and size", () => {
    expect(
      validateFile({ name: "a.pdf", type: "application/pdf", size: 100 }),
    ).toBeNull();
    expect(validateFile({ name: "a.png", type: "", size: 100 })).toBeNull();
    expect(
      validateFile({
        name: "a.pdf",
        type: "application/pdf",
        size: 5 * 1024 * 1024,
      })?.key,
    ).toBe("ob.v.fileSize");
    expect(
      validateFile({
        name: "a.exe",
        type: "application/x-msdownload",
        size: 10,
      })?.key,
    ).toBe("ob.v.fileType");
    expect(
      validateFile({ name: "a.pdf", type: "application/pdf", size: 0 })?.key,
    ).toBe("ob.v.fileEmpty");
  });
});

const buyer = {
  legal_name: "Dhaka Traders Ltd",
  trade_license_no: "TRAD/DNCC/012345/2024",
  license_authority: "Dhaka North City Corporation",
  license_expiry: "2027-06-30",
  irc_no: "BA-0123456",
  tin: "123456789012",
  "address.division": "Dhaka",
  "address.district": "Dhaka",
  "address.upazila": "Gulshan",
  "address.street": "House 1, Road 2",
  business_type: "TRADER",
  main_import_goods: "LED lights",
  monthly_import_volume: "500K_2M_BDT",
};
const supplier = {
  legal_name_en: "Shenzhen Bright Co",
  legal_name_zh: "深圳明亮有限公司",
  uscc: "91350100M000100Y43",
  "address.province": "广东",
  "address.city": "深圳",
  "address.district": "南山",
  business_scope: "LED lighting",
  export_experience_years: "6",
  "bank.bank_name": "Bank of China",
  "bank.holder_name": "Shenzhen Bright Co",
  "bank.account_no": "6217000012345678",
  "bank.currency": "USD",
  "bank.swift": "BKCHCNBJ",
};

describe("business validation", () => {
  const now = new Date("2026-10-20T00:00:00Z");
  it("accepts complete buyer and supplier data", () => {
    expect(validateBusiness("BUYER", buyer, new Set(), now)).toEqual({});
    expect(validateBusiness("SUPPLIER", supplier, new Set(), now)).toEqual({});
  });
  it("reports field-level problems", () => {
    const e = validateBusiness(
      "BUYER",
      { ...buyer, license_expiry: "2020-01-01", tin: "12", irc_no: "" },
      new Set(),
      now,
    );
    expect(e.license_expiry?.key).toBe("ob.v.expired");
    expect(e.tin?.key).toBe("ob.v.tin");
    expect(e.irc_no?.key).toBe("ob.v.required");
    const s = validateBusiness(
      "SUPPLIER",
      {
        ...supplier,
        uscc: "91350100M000100Y44",
        "bank.swift": "BKCH",
        "bank.currency": "EUR",
      },
      new Set(),
      now,
    );
    expect(s.uscc?.key).toBe("ob.v.usccCheck");
    expect(s["bank.swift"]?.key).toBe("ob.v.swift");
    expect(s["bank.currency"]?.key).toBe("ob.v.currency");
  });
  it("lets a saved (masked) sensitive value stay blank", () => {
    const { uscc: _u, ...rest } = supplier;
    void _u;
    expect(validateBusiness("SUPPLIER", rest, new Set(["uscc"]), now)).toEqual(
      {},
    );
    expect(validateBusiness("SUPPLIER", rest, new Set(), now).uscc?.key).toBe(
      "ob.v.required",
    );
  });
  it("nests dotted keys into the request body and upper-cases codes", () => {
    const body = toBusinessBody("SUPPLIER", {
      ...supplier,
      "bank.swift": "bkchcnbj",
    }) as unknown as Record<string, unknown>;
    expect(body.export_experience_years).toBe(6);
    expect(body.bank).toMatchObject({ swift: "BKCHCNBJ", currency: "USD" });
    expect(body.address).toMatchObject({ city: "深圳" });
  });
  it("prefills non-sensitive saved values and remembers masked ones", () => {
    const { values, masked } = draftFromBusiness("BUYER", {
      legal_name: "Dhaka Traders Ltd",
      tin_masked: "****9012",
      address: { division: "Dhaka" },
    });
    expect(values).toEqual({
      legal_name: "Dhaka Traders Ltd",
      "address.division": "Dhaka",
    });
    expect([...masked]).toEqual(["tin"]);
  });
});
