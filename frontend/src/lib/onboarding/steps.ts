import type { OnboardingState } from "@/lib/api/onboarding";

import { flatten, REQUIRED_DOCS } from "./validate";

export type WizardStep =
  "role" | "contact" | "business" | "documents" | "security" | "review";

export const ALL_STEPS: readonly WizardStep[] = [
  "role",
  "contact",
  "business",
  "documents",
  "security",
  "review",
];

/** Admins only see security (consent + TOTP) and review; everyone else walks all six. */
export const stepsFor = (
  role: OnboardingState["role"],
): readonly WizardStep[] => (role === "ADMIN" ? ["security", "review"] : ALL_STEPS);

export function docsDone(state: OnboardingState): boolean {
  if (state.role !== "BUYER" && state.role !== "SUPPLIER") return false;
  return REQUIRED_DOCS[state.role].every((type) =>
    state.documents.some((d) => d.type === type && d.status !== "REJECTED"),
  );
}

export function stepDone(state: OnboardingState, step: WizardStep): boolean {
  switch (step) {
    case "role":
      return state.role !== null;
    case "contact":
      return Boolean(state.contact?.phone_verified);
    case "business":
      return Object.keys(flatten(state.business)).length > 0;
    case "documents":
      return docsDone(state);
    case "security":
      return state.role === "ADMIN"
        ? state.mfa.enabled && Boolean(state.consent?.accepted_at)
        : Boolean(state.consent?.accepted_at);
    case "review":
      return (
        state.account_status === "PENDING_VERIFICATION" ||
        state.account_status === "ACTIVE"
      );
  }
}

export function firstOpenStep(state: OnboardingState): WizardStep {
  const list = stepsFor(state.role);
  return list.find((s) => !stepDone(state, s)) ?? list[list.length - 1];
}

export const isWizardStep = (v: string | null): v is WizardStep =>
  ALL_STEPS.includes(v as WizardStep);

/** Where a user with this state belongs when they are not editing the wizard. */
export function homeFor(state: OnboardingState): string | null {
  switch (state.account_status) {
    case "ACTIVE":
      return state.role === "SUPPLIER" ? "/supplier" : "/app";
    case "PENDING_VERIFICATION":
      return state.decision === "CHANGES_REQUESTED"
        ? null
        : "/onboarding/status";
    case "REJECTED":
      return "/account-status?reason=rejected";
    case "SUSPENDED":
      return "/account-status?reason=suspended";
    default:
      return null;
  }
}
