import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { MeContext } from "@/lib/MeContext";
import { markOnboardingSeen } from "@/lib/welcome";


import { setLang, user } from "./testUtils";
import { WelcomeTour } from "./WelcomeTour";

const mount = (role: "BUYER" | "SUPPLIER" = "BUYER", status = "ACTIVE") =>
  render(
    <I18nProvider>
      <MeContext.Provider
        value={{ ...user(role), account_status: status } as never}
      >
        <WelcomeTour />
      </MeContext.Provider>
    </I18nProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setLang("en");
});

describe("WelcomeTour", () => {
  it("does not appear for users who never went through onboarding (demo users)", () => {
    mount();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("appears once after onboarding, walks three steps and is not shown again", async () => {
    markOnboardingSeen();
    const { unmount } = mount();
    expect(
      await screen.findByRole("dialog", { name: "Welcome to Setu, Test" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Start with an order")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    const finish = screen.getByRole("link", { name: "Create my first order" });
    expect(finish.getAttribute("href")).toBe("/app/deals/new");
    fireEvent.click(finish);
    unmount();
    mount();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not show while the account is still being verified", () => {
    markOnboardingSeen();
    mount("BUYER", "PENDING_VERIFICATION");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("has no sample-data button", async () => {
    markOnboardingSeen();
    mount("BUYER");
    await screen.findByRole("dialog");
    expect(screen.queryByRole("button", { name: /sample data/i })).toBeNull();
  });
});
