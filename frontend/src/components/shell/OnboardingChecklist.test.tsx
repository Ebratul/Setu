import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "@/lib/api/auth";

import { OnboardingChecklist } from "./OnboardingChecklist";
import { trackVisit } from "./onboarding";
import { renderI18n, setLang, user } from "./testUtils";

vi.mock("@/lib/api/auth", () => ({ getMe: vi.fn() }));

beforeEach(() => {
  localStorage.clear();
  setLang("en");
});

describe("OnboardingChecklist", () => {
  it("shows the buyer's three steps with the scam simulator", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    renderI18n(<OnboardingChecklist />);
    expect(await screen.findByText("Try the Scam Simulator")).toBeInTheDocument();
    expect(screen.queryByText("Try the Attack Console")).toBeNull();
    expect(screen.getByText("0 of 3 done")).toBeInTheDocument();
  });

  it("shows the attack console for staff and ticks visited items", async () => {
    vi.mocked(getMe).mockResolvedValue(user("JUDGE"));
    renderI18n(<OnboardingChecklist />);
    await screen.findByText("Try the Attack Console");
    trackVisit("u-JUDGE", "/app/cashflow", "JUDGE");
    await waitFor(() => expect(screen.getByText("1 of 3 done")).toBeInTheDocument());
  });

  it("persists dismissal and can show the checklist again", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    const { unmount } = renderI18n(<OnboardingChecklist />);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.queryByTestId("onboarding")).toBeNull();
    unmount();
    renderI18n(<OnboardingChecklist />);
    const again = await screen.findByTestId("onboard-show");
    fireEvent.click(again);
    expect(await screen.findByTestId("onboarding")).toBeInTheDocument();
  });

  it("still renders when storage throws", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderI18n(<OnboardingChecklist />);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    expect(screen.getByTestId("onboard-show")).toBeInTheDocument();
    get.mockRestore();
    set.mockRestore();
  });

  it("is hidden for suppliers", async () => {
    vi.mocked(getMe).mockResolvedValue(user("SUPPLIER"));
    renderI18n(<OnboardingChecklist />);
    await waitFor(() => expect(getMe).toHaveBeenCalled());
    expect(screen.queryByTestId("onboarding")).toBeNull();
  });
});
