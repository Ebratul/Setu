import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from "./client";
import type { AccountStatus } from "./auth";

/*
 * P30 onboarding contract (docs/p30-design.md section 4). Hand-written until `make types` runs against the
 * finished backend; this is the only file to reconcile with the generated schema.
 */

export type OnboardingRole = "BUYER" | "SUPPLIER" | "ADMIN" | "JUDGE";
export type Lang = "en" | "bn" | "zh";
export type CheckStatus = "PASS" | "WARN" | "FAIL";
export type Decision =
  "APPROVED" | "CHANGES_REQUESTED" | "REJECTED" | "SUSPENDED" | null;
export type DocType =
  | "TRADE_LICENSE"
  | "IRC"
  | "TIN_CERT"
  | "BUSINESS_LICENSE"
  | "BANK_PROOF"
  | "OTHER";
export type DocStatus = "UPLOADED" | "VERIFIED" | "REJECTED";

export type PublicCheck = {
  code: string;
  status: CheckStatus;
  detail?: string | null;
};
export type DocumentOut = {
  id: string;
  type: DocType;
  original_name: string;
  mime: string;
  size: number;
  status: DocStatus;
  reviewer_notes?: string | null;
  created_at: string;
};
export type ChangeRequest = { target: string; note: string };
export type StepState = { key: string; done: boolean };

export type OnboardingState = {
  account_status: AccountStatus | null;
  role: OnboardingRole | null;
  step: number;
  steps: StepState[];
  contact: {
    full_name: string | null;
    designation: string | null;
    mobile_masked: string | null;
    phone_verified: boolean;
    language: Lang | null;
  } | null;
  /** Masked: sensitive values (licence no, IRC, TIN, USCC, account no) arrive as `****1234`. */
  business: Record<string, unknown> | null;
  documents: DocumentOut[];
  consent: { terms_version: string | null; accepted_at: string | null } | null;
  mfa: { enabled: boolean; required: boolean };
  checks: PublicCheck[];
  submitted_at: string | null;
  decision: Decision;
  change_requests: ChangeRequest[];
  terms_version: string;
  demo_mode: boolean;
  reason?: string | null;
};

export type ContactInput = {
  full_name: string;
  designation: string;
  mobile: string;
  language: Lang;
};
export type PhoneSent = {
  sent: boolean;
  expires_in_seconds: number;
  sends_left: number;
  demo_code?: string | null;
};

export type Address = {
  division?: string;
  district?: string;
  upazila?: string;
  street?: string;
  province?: string;
  city?: string;
};
export type BuyerBusiness = {
  legal_name: string;
  trade_name?: string | null;
  trade_license_no: string;
  license_authority: string;
  license_expiry: string;
  irc_no: string;
  tin: string;
  address: {
    division: string;
    district: string;
    upazila: string;
    street: string;
  };
  business_type: "MANUFACTURER" | "TRADER";
  main_import_goods: string;
  monthly_import_volume: string;
};
export type SupplierBusiness = {
  legal_name_en: string;
  legal_name_zh: string;
  uscc: string;
  address: {
    province: string;
    city: string;
    district: string;
    street?: string | null;
  };
  business_scope: string;
  export_experience_years: number;
  wechat_id?: string | null;
  contact_phone?: string | null;
  bank: {
    bank_name: string;
    holder_name: string;
    account_no: string;
    currency: "CNY" | "USD";
    swift: string;
  };
};
export type BusinessInput = BuyerBusiness | SupplierBusiness;
export type ConsentInput = {
  terms_version: string;
  accept_terms: true;
  accept_privacy: true;
  consent_verification: true;
};

const fresh = (signal?: AbortSignal) => ({
  signal,
  cache: "no-store" as const,
});
const put = <T>(path: string, body: unknown) => apiPut<T>(path, body);

export const getOnboardingState = (signal?: AbortSignal) =>
  apiGet<OnboardingState>("/onboarding/me", fresh(signal));
export const selectRole = (role: OnboardingRole, invite_code?: string) =>
  apiPost<OnboardingState>(
    "/onboarding/role",
    invite_code ? { role, invite_code } : { role },
  );
export const saveContact = (body: ContactInput) =>
  put<OnboardingState>("/onboarding/contact", body);
export const sendPhoneCode = () => apiPost<PhoneSent>("/onboarding/phone/send");
export const verifyPhoneCode = (code: string) =>
  apiPost<OnboardingState>("/onboarding/phone/verify", { code });
export const saveBusiness = (body: BusinessInput) =>
  put<OnboardingState>("/onboarding/business", body);
export const saveConsent = (body: ConsentInput) =>
  put<OnboardingState>("/onboarding/consent", body);
export const submitProfile = () =>
  apiPost<OnboardingState>("/onboarding/submit");

export function uploadDocument(type: DocType, file: File) {
  const form = new FormData();
  form.set("type", type);
  form.set("file", file);
  return apiPostForm<DocumentOut>("/onboarding/documents", form);
}
export const deleteDocument = (id: string) =>
  apiDelete<void>(`/onboarding/documents/${id}`);
export const documentUrl = (id: string) =>
  apiGet<{ url: string; expires_at?: number }>(
    `/onboarding/documents/${id}/url`,
    fresh(),
  );

/* Admin review */
export type ReviewStatus = "PENDING" | "CHANGES_REQUESTED" | "APPROVED" | "REJECTED" | "SUSPENDED";
export type ReviewFilter = ReviewStatus;
export type Recommendation = "AUTO_CLEAR" | "NEEDS_REVIEW" | "BLOCK";
export type ReviewCheck = { code: string; status: CheckStatus; detail: string };
export type RevealableField = "mobile" | "trade_license_no" | "irc_no" | "tin" | "uscc" | "bank_account_no";
export type ReviewDetail = {
  id: string;
  status: ReviewStatus;
  role: "BUYER" | "SUPPLIER";
  account_status: AccountStatus | null;
  decision: Decision;
  recommendation: Recommendation;
  score: number;
  user_id: string;
  user_email: string;
  user_display_name: string;
  party: { legal_name: string; city?: string | null; country?: string | null } | null;
  contact: { full_name?: string | null; designation?: string | null; mobile_masked?: string | null; phone_verified?: boolean } | null;
  business: Record<string, unknown> | null;
  documents: DocumentOut[];
  change_requests: ChangeRequest[];
  checks: ReviewCheck[];
  submitted_at: string;
  decided_at: string | null;
  reason: string | null;
};
export type ReviewItem = ReviewDetail;
export type ReviewList = { items: ReviewItem[] };
export type ChangeItem = { target: string; note: string };

const withStep = (token: string | null): RequestInit | undefined =>
  token ? { headers: { "X-Stepup": token } } : undefined;

export function listReviews(status: ReviewFilter | undefined, role: "BUYER" | "SUPPLIER" | undefined, signal?: AbortSignal) {
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  if (role) q.set("role", role);
  const qs = q.toString();
  return apiGet<ReviewList>(`/admin/onboarding${qs ? `?${qs}` : ""}`, fresh(signal));
}
export const getReview = (id: string, signal?: AbortSignal) => apiGet<ReviewDetail>(`/admin/onboarding/${id}`, fresh(signal));
export const revealField = (id: string, field: RevealableField, reason: string) =>
  apiPost<{ field: string; value: string }>(`/admin/onboarding/${id}/reveal`, { field, reason });
export const approveReview = (id: string, step: string | null = null) =>
  apiPost<ReviewDetail>(`/admin/onboarding/${id}/approve`, undefined, withStep(step));
export const requestChanges = (id: string, items: ChangeItem[], step: string | null = null) =>
  apiPost<ReviewDetail>(`/admin/onboarding/${id}/request-changes`, { items }, withStep(step));
export const rejectReview = (id: string, reason: string, step: string | null = null) =>
  apiPost<ReviewDetail>(`/admin/onboarding/${id}/reject`, { reason }, withStep(step));
export const suspendReview = (id: string, reason: string, step: string | null = null) =>
  apiPost<ReviewDetail>(`/admin/onboarding/${id}/suspend`, { reason }, withStep(step));
export const autoApproveReview = (id: string) => apiPost<ReviewDetail>(`/admin/onboarding/${id}/auto-approve`);
