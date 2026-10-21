import type { OnboardingState } from "@/lib/api/onboarding";

export type StepProps = {
  state: OnboardingState;
  onState: (next: OnboardingState) => void;
  /** The role step passes the updated state, because the step list depends on the chosen role. */
  onNext: (updated?: OnboardingState) => void;
};
