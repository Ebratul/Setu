import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";
import { baseState } from "@/lib/onboarding/testState";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => Promise.resolve("neon"),
  getPublicAuthConfig: () =>
    Promise.resolve({ mode: "neon", demoEnabled: false, googleEnabled: true }),
}));
const getState = vi.hoisted(() => vi.fn());
const selectRole = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/onboarding", () => ({
  getOnboardingState: getState,
  saveContact: vi.fn(),
  sendPhoneCode: vi.fn(),
  verifyPhoneCode: vi.fn(),
  selectRole: selectRole,
  saveBusiness: vi.fn(),
  saveConsent: vi.fn(),
  submitProfile: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
}));
vi.mock("@/lib/auth/flow", async (orig) => ({
  ...(await orig<typeof import("@/lib/auth/flow")>()),
  signOutEverywhere: vi.fn(),
}));

import { OnboardingWizard } from "./OnboardingWizard";

beforeEach(() => {
  vi.clearAllMocks();
  search = "";
  localStorage.clear();
  setLang("en");
});

describe("OnboardingWizard", () => {
  it("starts at the role step for a new user", async () => {
    getState.mockResolvedValue({
      ...baseState,
      account_status: null,
      role: null,
      contact: null,
    });
    renderI18n(<OnboardingWizard />);
    expect(
      await screen.findByRole("heading", { name: /Step 1 of 6: Your role/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole("list", { name: "Account setup steps" }),
    ).toBeTruthy();
  });

  it("resumes at the first unfinished step", async () => {
    getState.mockResolvedValue(baseState);
    renderI18n(<OnboardingWizard />);
    expect(
      await screen.findByRole("heading", {
        name: /Step 2 of 6: Contact and phone/,
      }),
    ).toBeTruthy();
    expect(localStorage.getItem("setu_onboarding_seen")).toBe("1");
  });

  it("honours the ?step= deep link and shows the change-request banner", async () => {
    search = "step=business";
    getState.mockResolvedValue({
      ...baseState,
      account_status: "PENDING_VERIFICATION",
      decision: "CHANGES_REQUESTED",
      change_requests: [{ target: "tin", note: "unclear" }],
    });
    renderI18n(<OnboardingWizard />);
    expect(
      await screen.findByRole("heading", { name: /Step 3 of 6: Business/ }),
    ).toBeTruthy();
    expect(screen.getByText(/asked for 1 change/)).toBeTruthy();
  });

  it("shows only the security step for an administrator", async () => {
    getState.mockResolvedValue({ ...baseState, role: "ADMIN" });
    renderI18n(<OnboardingWizard />);
    expect(
      await screen.findByRole("heading", {
        name: /Step 1 of 2: Security and consent/,
      }),
    ).toBeTruthy();
  });

  it.each([
    [{ account_status: "PENDING_VERIFICATION" }, "/onboarding/status"],
    [{ account_status: "ACTIVE" }, "/app"],
    [{ account_status: "SUSPENDED" }, "/account-status?reason=suspended"],
  ])("redirects %o to %s", async (over, path) => {
    getState.mockResolvedValue({ ...baseState, ...over });
    renderI18n(<OnboardingWizard />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith(path));
  });

  it("sends a signed-out visitor to the login page", async () => {
    getState.mockRejectedValue(new ApiError(401, "x", null, "UNAUTHENTICATED"));
    renderI18n(<OnboardingWizard />);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/login?next=/onboarding"),
    );
  });

  it("goes back a step with the Back button", async () => {
    getState.mockResolvedValue(baseState);
    renderI18n(<OnboardingWizard />);
    await screen.findByRole("heading", { name: /Step 2 of 6/ });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(
      await screen.findByRole("heading", { name: /Step 1 of 6: Your role/ }),
    ).toBeTruthy();
  });

  it("opens the Security step right after an administrator picks the role", async () => {
    getState.mockResolvedValue({ ...baseState, account_status: null, role: null, contact: null });
    selectRole.mockResolvedValue({ ...baseState, role: "ADMIN", contact: null });
    renderI18n(<OnboardingWizard />);
    fireEvent.click(await screen.findByLabelText(/^Administrator/));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("heading", { name: /Step 1 of 2: Security and consent/ })).toBeTruthy();
  });

  it("offers the Chinese language option in the auth shell", async () => {
    getState.mockResolvedValue(baseState);
    renderI18n(<OnboardingWizard />);
    await screen.findByRole("heading", { name: /Step 2 of 6/ });
    expect(screen.getAllByText("中文").length).toBeGreaterThan(0);
  });
});
