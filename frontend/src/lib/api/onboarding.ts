import type { components, operations } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type OnboardingInput = S["OnboardingIn"];
export type BankAccountInput = S["BankAccountIn"];
export type OnboardingState = S["OnboardingStatusOut"];
export type PublicCheck = S["PublicCheck"];
export type Review = S["ReviewOut"];
export type ReviewList = S["ReviewList"];
export type ReviewCheck = S["AdminCheck"];
export type ReviewStatus = S["OnboardingStatus"];
export type Recommendation = Review["recommendation"];
export type RejectInput = S["app__schemas__onboarding__RejectIn"];
export type ReviewFilter = NonNullable<
  NonNullable<operations["list_reviews_admin_onboarding_get"]["parameters"]["query"]>["status"]
>;

const fresh = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

export const submitOnboarding = (body: OnboardingInput) => apiPost<OnboardingState>("/onboarding", body);
export const getOnboardingStatus = (signal?: AbortSignal) =>
  apiGet<OnboardingState>("/onboarding/status", fresh(signal));

export function listReviews(status: ReviewFilter | undefined, signal?: AbortSignal) {
  const q = status ? `?status=${status}` : "";
  return apiGet<ReviewList>(`/admin/onboarding${q}`, fresh(signal));
}
export const getReview = (id: string, signal?: AbortSignal) =>
  apiGet<Review>(`/admin/onboarding/${id}`, fresh(signal));
export const approveReview = (id: string) => apiPost<Review>(`/admin/onboarding/${id}/approve`);
export const rejectReview = (id: string, reason: string) =>
  apiPost<Review>(`/admin/onboarding/${id}/reject`, { reason } satisfies RejectInput);
