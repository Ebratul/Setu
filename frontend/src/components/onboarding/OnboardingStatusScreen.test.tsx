import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang, user } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => Promise.resolve("neon"),
  endAuthSession: vi.fn(),
}));
const startSession = vi.fn();
vi.mock("@/lib/api/auth", () => ({ startSession: () => startSession(), logout: vi.fn() }));
const getOnboardingStatus = vi.fn();
vi.mock("@/lib/api/onboarding", () => ({ getOnboardingStatus: () => getOnboardingStatus() }));

import { OnboardingStatusScreen, STATUS_POLL_MS } from "./OnboardingStatusScreen";

const state = (over: Record<string, unknown> = {}) => ({
  status: "PENDING",
  account_status: "PENDING",
  role: "BUYER",
  party_name: "Rahim Traders Ltd",
  checks: [
    { code: "TAX_ID_FORMAT", status: "PASS", detail: "ok" },
    { code: "SANCTIONS_SCREEN", status: "PASS", detail: "hidden" },
    { code: "HOLDER_NAME_MATCH", status: "WARN", detail: "x" },
  ],
  submitted_at: null,
  decided_at: null,
  reason: null,
  ...over,
});

const fakeIntervals = () => vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });

function setVisibility(v: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => v });
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

async function settle() {
  for (let i = 0; i < 6; i++) await flush();
}

describe("OnboardingStatusScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setLang("en");
    setVisibility("visible");
  });
  afterEach(() => vi.useRealTimers());

  it("lists the public checks (never a sanctions check) and the review state", async () => {
    getOnboardingStatus.mockResolvedValue(state());
    renderI18n(<OnboardingStatusScreen />);
    expect(await screen.findByText("Waiting for review")).toBeInTheDocument();
    expect(screen.getByText("Tax ID format")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.queryByText(/anction/)).toBeNull();
    expect(screen.queryByText(/score/i)).toBeNull();
  });

  it("polls every 20 s while pending, pauses while hidden", async () => {
    getOnboardingStatus.mockResolvedValue(state());
    fakeIntervals();
    renderI18n(<OnboardingStatusScreen />);
    await screen.findByText("Waiting for review");
    expect(getOnboardingStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(STATUS_POLL_MS);
    });
    await flush();
    expect(getOnboardingStatus).toHaveBeenCalledTimes(2);
    setVisibility("hidden");
    await act(async () => {
      vi.advanceTimersByTime(STATUS_POLL_MS * 3);
    });
    expect(getOnboardingStatus).toHaveBeenCalledTimes(2);
  });

  it("stops polling and opens the session when approved and active", async () => {
    getOnboardingStatus.mockResolvedValue(state({ status: "APPROVED", account_status: "ACTIVE" }));
    startSession.mockResolvedValue(user("SUPPLIER"));
    fakeIntervals();
    renderI18n(<OnboardingStatusScreen />);
    await settle();
    expect(replace).toHaveBeenCalledWith("/supplier");
    expect(startSession).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(STATUS_POLL_MS * 2);
    });
    expect(getOnboardingStatus).toHaveBeenCalledTimes(1);
  });

  it("sends a buyer to /app", async () => {
    getOnboardingStatus.mockResolvedValue(state({ status: "APPROVED", account_status: "ACTIVE" }));
    startSession.mockResolvedValue(user("BUYER"));
    renderI18n(<OnboardingStatusScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app"));
  });

  it("hands a rejected applicant to the account-status screen and stops polling", async () => {
    getOnboardingStatus.mockResolvedValue(state({ status: "REJECTED", account_status: "SUSPENDED", reason: "No licence" }));
    fakeIntervals();
    renderI18n(<OnboardingStatusScreen />);
    await settle();
    expect(replace).toHaveBeenCalledWith("/account-status?reason=suspended");
    await act(async () => {
      vi.advanceTimersByTime(STATUS_POLL_MS * 2);
    });
    expect(getOnboardingStatus).toHaveBeenCalledTimes(1);
    expect(startSession).not.toHaveBeenCalled();
  });

  it("goes to the form when there is no application yet", async () => {
    getOnboardingStatus.mockRejectedValue(new ApiError(404, "x", null, "NOT_ONBOARDED"));
    renderI18n(<OnboardingStatusScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding"));
  });
});
