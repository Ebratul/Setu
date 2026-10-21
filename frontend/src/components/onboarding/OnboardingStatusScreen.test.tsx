import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { baseState } from "@/lib/onboarding/testState";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => Promise.resolve("neon"),
  getPublicAuthConfig: () =>
    Promise.resolve({ mode: "neon", demoEnabled: false, googleEnabled: true }),
}));
const getState = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/onboarding", () => ({ getOnboardingState: getState }));
vi.mock("@/lib/auth/flow", async (orig) => ({
  ...(await orig<typeof import("@/lib/auth/flow")>()),
  signOutEverywhere: vi.fn(),
}));

import { OnboardingStatusScreen } from "./OnboardingStatusScreen";

const pending = {
  ...baseState,
  account_status: "PENDING_VERIFICATION" as const,
  contact: { ...baseState.contact!, phone_verified: true },
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setLang("en");
});

describe("OnboardingStatusScreen", () => {
  it("shows Verification in progress with a checklist and hides sanctions checks", async () => {
    getState.mockResolvedValue({
      ...pending,
      checks: [
        { code: "PHONE_VERIFIED", status: "PASS" },
        { code: "SANCTIONS_SCREEN", status: "FAIL" },
      ],
    });
    renderI18n(<OnboardingStatusScreen />);
    expect(await screen.findByText("Verification in progress")).toBeTruthy();
    expect(screen.getByText("Review by a Setu reviewer")).toBeTruthy();
    expect(screen.queryByText(/SANCTION/i)).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("lists change requests with deep links to the right step and a resubmit link", async () => {
    getState.mockResolvedValue({
      ...pending,
      decision: "CHANGES_REQUESTED",
      change_requests: [
        { target: "IRC", note: "Photo is blurry" },
        { target: "tin", note: "Digits missing" },
      ],
    });
    renderI18n(<OnboardingStatusScreen />);
    expect(await screen.findByText("Changes requested")).toBeTruthy();
    expect(screen.getByText("Photo is blurry")).toBeTruthy();
    expect(
      screen
        .getByRole("link", {
          name: /Fix this: Import Registration Certificate/,
        })
        .getAttribute("href"),
    ).toBe("/onboarding?step=documents");
    expect(
      screen.getByRole("link", { name: /Fix this: TIN/ }).getAttribute("href"),
    ).toBe("/onboarding?step=business");
    expect(
      screen
        .getByRole("link", { name: "Go to review and resubmit" })
        .getAttribute("href"),
    ).toBe("/onboarding?step=review");
  });

  it.each([
    [{ account_status: "REJECTED" }, "/account-status?reason=rejected"],
    [{ account_status: "SUSPENDED" }, "/account-status?reason=suspended"],
    [{ account_status: "ACTIVE" }, "/app"],
    [{ account_status: "PENDING_PROFILE" }, "/onboarding"],
  ])("sends %o to %s", async (over, path) => {
    getState.mockResolvedValue({ ...baseState, ...over });
    renderI18n(<OnboardingStatusScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith(path));
  });
});
