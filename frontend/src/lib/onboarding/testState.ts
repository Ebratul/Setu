import type { OnboardingState } from "@/lib/api/onboarding";

export const baseState: OnboardingState = {
  account_status: "PENDING_PROFILE",
  role: "BUYER",
  step: 1,
  steps: [],
  contact: {
    full_name: "Rahim",
    designation: "Director",
    mobile_masked: "01*******78",
    phone_verified: false,
    language: "en",
  },
  business: null,
  documents: [],
  consent: null,
  mfa: { enabled: false, required: false },
  checks: [],
  submitted_at: null,
  decision: null,
  change_requests: [],
  terms_version: "2026-10",
  demo_mode: false,
};
