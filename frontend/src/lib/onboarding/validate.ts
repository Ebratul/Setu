import type {
  BusinessInput,
  ContactInput,
  Lang,
  OnboardingRole,
} from "@/lib/api/onboarding";

export type FieldError = {
  key: string;
  vars?: Record<string, string | number>;
};
export type Errors = Record<string, FieldError>;
export type Values = Record<string, string>;

export type FieldDef = {
  key: string;
  kind: "text" | "textarea" | "select" | "date" | "number";
  required: boolean;
  max: number;
  /** Sensitive values come back masked from the API, so they cannot be prefilled. */
  sensitive?: boolean;
  options?: readonly string[];
  zh?: boolean;
  inputMode?: "numeric" | "text" | "tel";
  autoComplete?: string;
  upper?: boolean;
};

export const USCC_ALPHABET = "0123456789ABCDEFGHJKLMNPQRTUWXY";
const USCC_WEIGHTS = [
  1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28,
];

/** GB 32100-2015 unified social credit code: 18 chars from the alphabet with a mod-31 check character. */
export function isValidUscc(raw: string): boolean {
  const v = raw.trim().toUpperCase();
  if (v.length !== 18) return false;
  let sum = 0;
  for (let i = 0; i < 17; i++) {
    const idx = USCC_ALPHABET.indexOf(v[i]);
    if (idx < 0) return false;
    sum += USCC_WEIGHTS[i] * idx;
  }
  const check = (31 - (sum % 31)) % 31;
  return USCC_ALPHABET[check] === v[17];
}

const BD_MOBILE = /^\+8801[3-9]\d{8}$/;
const E164 = /^\+[1-9]\d{7,14}$/;
const SWIFT = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
const BD_LICENSE = /^[A-Za-z0-9/-]{5,32}$/;
const BD_IRC = /^[A-Za-z0-9/-]{5,32}$/;
const BD_TIN = /^\d{9,13}$/;
const ACCOUNT_NO = /^[A-Za-z0-9]{6,34}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const isBdMobile = (v: string) => BD_MOBILE.test(v.trim());

/** Accepts 01712345678, 8801712345678, +880 1712-345678 and returns +8801712345678 when it can. */
export function normalizeMobile(raw: string): string {
  const s = raw.replace(/[\s\-()]/g, "");
  if (/^01\d{9}$/.test(s)) return `+88${s}`;
  if (/^8801\d{9}$/.test(s)) return `+${s}`;
  return s;
}

export function isFutureDate(v: string, now: Date = new Date()): boolean {
  if (!ISO_DATE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== v)
    return false;
  const today = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  );
  return d.getTime() > today;
}

export const MONTHLY_VOLUMES = ["UNDER_500K_BDT", "500K_2M_BDT", "2M_10M_BDT", "OVER_10M_BDT"] as const;

export const BUYER_FIELDS: FieldDef[] = [
  {
    key: "legal_name",
    kind: "text",
    required: true,
    max: 200,
    autoComplete: "organization",
  },
  { key: "trade_name", kind: "text", required: false, max: 200 },
  {
    key: "trade_license_no",
    kind: "text",
    required: true,
    max: 40,
    sensitive: true,
    upper: true,
  },
  { key: "license_authority", kind: "text", required: true, max: 120 },
  { key: "license_expiry", kind: "date", required: true, max: 10 },
  {
    key: "irc_no",
    kind: "text",
    required: true,
    max: 25,
    sensitive: true,
    upper: true,
  },
  {
    key: "tin",
    kind: "text",
    required: true,
    max: 13,
    sensitive: true,
    inputMode: "numeric",
  },
  { key: "address.division", kind: "text", required: true, max: 80 },
  { key: "address.district", kind: "text", required: true, max: 80 },
  { key: "address.upazila", kind: "text", required: true, max: 80 },
  {
    key: "address.street",
    kind: "text",
    required: true,
    max: 200,
    autoComplete: "street-address",
  },
  {
    key: "business_type",
    kind: "select",
    required: true,
    max: 20,
    options: ["MANUFACTURER", "TRADER"],
  },
  { key: "main_import_goods", kind: "text", required: true, max: 200 },
  {
    key: "monthly_import_volume",
    kind: "select",
    required: true,
    max: 20,
    options: MONTHLY_VOLUMES,
  },
];

export const SUPPLIER_FIELDS: FieldDef[] = [
  { key: "legal_name_en", kind: "text", required: true, max: 200 },
  { key: "legal_name_zh", kind: "text", required: true, max: 200, zh: true },
  {
    key: "uscc",
    kind: "text",
    required: true,
    max: 18,
    sensitive: true,
    upper: true,
  },
  { key: "address.province", kind: "text", required: true, max: 80, zh: true },
  { key: "address.city", kind: "text", required: true, max: 80, zh: true },
  { key: "address.district", kind: "text", required: true, max: 80, zh: true },
  { key: "address.street", kind: "text", required: false, max: 200, zh: true },
  {
    key: "business_scope",
    kind: "textarea",
    required: true,
    max: 500,
    zh: true,
  },
  {
    key: "export_experience_years",
    kind: "number",
    required: true,
    max: 2,
    inputMode: "numeric",
  },
  { key: "wechat_id", kind: "text", required: false, max: 60 },
  {
    key: "contact_phone",
    kind: "text",
    required: false,
    max: 20,
    inputMode: "tel",
  },
  { key: "bank.bank_name", kind: "text", required: true, max: 120 },
  { key: "bank.holder_name", kind: "text", required: true, max: 200 },
  {
    key: "bank.account_no",
    kind: "text",
    required: true,
    max: 34,
    sensitive: true,
  },
  {
    key: "bank.currency",
    kind: "select",
    required: true,
    max: 3,
    options: ["CNY", "USD"],
  },
  { key: "bank.swift", kind: "text", required: true, max: 11, upper: true },
];

export const fieldsFor = (role: OnboardingRole | null): FieldDef[] =>
  role === "SUPPLIER" ? SUPPLIER_FIELDS : role === "BUYER" ? BUYER_FIELDS : [];

const REQUIRED: FieldError = { key: "ob.v.required" };

function text(v: string, min: number, max: number): FieldError | null {
  const s = v.trim();
  if (!s) return REQUIRED;
  if (s.length < min || s.length > max)
    return { key: "ob.v.length", vars: { min, max } };
  return null;
}

export function validateContact(
  v: Values,
  role: OnboardingRole | null,
): Errors {
  const e: Errors = {};
  const n = text(v.full_name ?? "", 2, 120);
  if (n) e.full_name = n;
  const d = text(v.designation ?? "", 2, 80);
  if (d) e.designation = d;
  const m = normalizeMobile(v.mobile ?? "");
  if (!m) e.mobile = REQUIRED;
  else if (role === "SUPPLIER" ? !E164.test(m) : !BD_MOBILE.test(m))
    e.mobile = { key: role === "SUPPLIER" ? "ob.v.mobileIntl" : "ob.v.mobile" };
  return e;
}

function validateOne(def: FieldDef, raw: string, now: Date): FieldError | null {
  const v = raw.trim();
  if (!v) return def.required ? REQUIRED : null;
  switch (def.key) {
    case "trade_license_no":
      return BD_LICENSE.test(v) ? null : { key: "ob.v.license" };
    case "irc_no":
      return BD_IRC.test(v) ? null : { key: "ob.v.irc" };
    case "tin":
      return BD_TIN.test(v) ? null : { key: "ob.v.tin" };
    case "license_expiry":
      if (!ISO_DATE.test(v)) return { key: "ob.v.date" };
      return isFutureDate(v, now) ? null : { key: "ob.v.expired" };
    case "legal_name_zh":
      if (!/[\u4e00-\u9fff]/.test(v)) return { key: "ob.v.needsChinese" };
      return text(v, 2, def.max);
    case "uscc":
      if (v.length !== 18) return { key: "ob.v.usccLength" };
      return isValidUscc(v) ? null : { key: "ob.v.usccCheck" };
    case "export_experience_years":
      return /^\d{1,2}$/.test(v) ? null : { key: "ob.v.years" };
    case "contact_phone":
      return E164.test(normalizeMobile(v)) ? null : { key: "ob.v.mobileIntl" };
    case "bank.account_no":
      return ACCOUNT_NO.test(v) ? null : { key: "ob.v.account" };
    case "bank.swift":
      return SWIFT.test(v.toUpperCase()) ? null : { key: "ob.v.swift" };
    case "bank.currency":
      return v === "CNY" || v === "USD" ? null : { key: "ob.v.currency" };
  }
  if (def.kind === "select")
    return def.options?.includes(v) ? null : { key: "ob.v.choose" };
  return text(v, 2, def.max);
}

/** `masked` lists sensitive keys that are already saved on the server; they may stay blank to keep the saved value. */
export function validateBusiness(
  role: OnboardingRole | null,
  v: Values,
  masked: ReadonlySet<string> = new Set(),
  now: Date = new Date(),
): Errors {
  const e: Errors = {};
  for (const def of fieldsFor(role)) {
    const raw = v[def.key] ?? "";
    if (def.sensitive && !raw.trim() && masked.has(def.key)) continue;
    const err = validateOne(def, raw, now);
    if (err) e[def.key] = err;
  }
  return e;
}

export const REQUIRED_DOCS: Record<"BUYER" | "SUPPLIER", readonly string[]> = {
  BUYER: ["TRADE_LICENSE", "IRC"],
  SUPPLIER: ["BUSINESS_LICENSE", "BANK_PROOF"],
};
export const OPTIONAL_DOCS: Record<"BUYER" | "SUPPLIER", readonly string[]> = {
  BUYER: ["TIN_CERT", "OTHER"],
  SUPPLIER: ["OTHER"],
};

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;
export const UPLOAD_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
] as const;

export function validateFile(file: {
  size: number;
  type: string;
  name: string;
}): FieldError | null {
  if (file.size === 0) return { key: "ob.v.fileEmpty" };
  if (file.size > MAX_UPLOAD_BYTES) return { key: "ob.v.fileSize" };
  const type =
    file.type ||
    (/\.pdf$/i.test(file.name)
      ? "application/pdf"
      : /\.png$/i.test(file.name)
        ? "image/png"
        : /\.jpe?g$/i.test(file.name)
          ? "image/jpeg"
          : "");
  if (!(UPLOAD_TYPES as readonly string[]).includes(type))
    return { key: "ob.v.fileType" };
  return null;
}

export const looksMasked = (s: string) => /^[*•]|\*{2,}/.test(s);

export function flatten(
  obj: Record<string, unknown> | null | undefined,
  prefix = "",
  out: Values = {},
): Values {
  for (const [k, val] of Object.entries(obj ?? {})) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (val && typeof val === "object" && !Array.isArray(val))
      flatten(val as Record<string, unknown>, key, out);
    else if (val !== null && val !== undefined) out[key] = String(val);
  }
  return out;
}

/** Splits saved business data into prefill values and the set of sensitive keys that are saved but masked. */
/** The API echoes sensitive values as `<key>_masked` (bank.account_no as bank.account_masked). */
export function savedValue(flat: Values, key: string): string | undefined {
  if (flat[key] !== undefined) return flat[key];
  const alt = key === "bank.account_no" ? "bank.account_masked" : `${key}_masked`;
  return flat[alt];
}

export function draftFromBusiness(
  role: OnboardingRole | null,
  business: Record<string, unknown> | null,
): { values: Values; masked: Set<string> } {
  const flat = flatten(business);
  const values: Values = {};
  const masked = new Set<string>();
  for (const def of fieldsFor(role)) {
    const raw = savedValue(flat, def.key);
    if (raw === undefined || raw === "") continue;
    if (def.sensitive || looksMasked(raw)) masked.add(def.key);
    else values[def.key] = raw;
  }
  return { values, masked };
}

function nest(v: Values): Record<string, unknown> {
  const out: Record<string, Record<string, unknown> | unknown> = {};
  for (const [k, raw] of Object.entries(v)) {
    const val = raw.trim();
    const [head, tail] = k.split(".");
    if (tail) {
      const bucket = (out[head] ??= {}) as Record<string, unknown>;
      bucket[tail] = val;
    } else out[head] = val;
  }
  return out;
}

export function toBusinessBody(
  role: "BUYER" | "SUPPLIER",
  v: Values,
): BusinessInput {
  const body = nest(
    Object.fromEntries(Object.entries(v).filter(([, x]) => x.trim() !== "")),
  );
  for (const def of fieldsFor(role))
    if (def.upper && typeof v[def.key] === "string")
      setPath(body, def.key, v[def.key].trim().toUpperCase());
  if (role === "SUPPLIER") {
    body.export_experience_years = Number(v.export_experience_years ?? 0);
    if (v.contact_phone?.trim())
      body.contact_phone = normalizeMobile(v.contact_phone);
  }
  return body as unknown as BusinessInput;
}

function setPath(o: Record<string, unknown>, key: string, val: string) {
  const [h, t] = key.split(".");
  if (!t) o[h] = val;
  else ((o[h] ??= {}) as Record<string, unknown>)[t] = val;
}

export function toContactBody(v: Values, language: Lang): ContactInput {
  return {
    full_name: (v.full_name ?? "").trim(),
    designation: (v.designation ?? "").trim(),
    mobile: normalizeMobile(v.mobile ?? ""),
    language,
  };
}

/** Server field path ("address.district", "body.bank.swift") -> our key; unknown paths map to null. */
export function serverFieldKey(
  path: string,
  known: readonly string[],
): string | null {
  const p = path.replace(/^body\./, "");
  return known.includes(p) ? p : null;
}

export function isValidTotp(code: string): boolean {
  return /^\d{6}$/.test(code.trim());
}
