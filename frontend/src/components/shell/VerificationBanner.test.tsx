import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";
import { ACCOUNT_BLOCK_EVENT, NOT_VERIFIED_EVENT } from "@/lib/api/client";
import { MeContext } from "@/lib/MeContext";
import { useMoneyGate } from "@/lib/useAccountGate";

import { NotVerifiedListener } from "./NotVerifiedListener";
import { setLang, user } from "./testUtils";
import { VerificationBanner } from "./VerificationBanner";

const as = (
  status: string | undefined,
  role: "BUYER" | "ADMIN" | "SUPPLIER" = "BUYER",
) => ({ ...user(role), account_status: status }) as never;

function Gate() {
  const g = useMoneyGate();
  return <button disabled={!g.allowed}>{g.reason ?? "ok"}</button>;
}

function wrap(me: unknown, ui: React.ReactNode) {
  return render(
    <I18nProvider>
      <ToastProvider>
        <MeContext.Provider value={me as never}>{ui}</MeContext.Provider>
      </ToastProvider>
    </I18nProvider>,
  );
}

beforeEach(() => setLang("en"));

describe("VerificationBanner", () => {
  it("is hidden for ACTIVE and for users without a status", () => {
    wrap(as("ACTIVE"), <VerificationBanner />);
    expect(screen.queryByTestId("verification-banner")).toBeNull();
  });
  it("says what is locked and links to the status page while in review", () => {
    wrap(as("PENDING_VERIFICATION"), <VerificationBanner />);
    expect(screen.getByText("Verification in progress")).toBeTruthy();
    expect(screen.getByText("Creating real orders")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "View status" }).getAttribute("href"),
    ).toBe("/onboarding/status");
  });
  it("sends an unfinished profile back to setup", () => {
    wrap(as("PENDING_PROFILE"), <VerificationBanner />);
    expect(
      screen.getByRole("link", { name: "Continue setup" }).getAttribute("href"),
    ).toBe("/onboarding");
  });
  it("asks administrators for two-factor authentication", () => {
    wrap(as("PENDING_PROFILE", "ADMIN"), <VerificationBanner />);
    expect(
      screen.getByRole("link", { name: "Set up now" }).getAttribute("href"),
    ).toBe("/onboarding?step=security");
  });
});

describe("money gate and 403 handling", () => {
  it("disables money buttons with a reason until ACTIVE", () => {
    const { unmount } = wrap(as("PENDING_VERIFICATION"), <Gate />);
    const b = screen.getByRole("button");
    expect(b).toHaveProperty("disabled", true);
    expect(b.textContent).toBe("Locked until your account is verified.");
    unmount();
    wrap(as("ACTIVE"), <Gate />);
    expect(screen.getByRole("button")).toHaveProperty("disabled", false);
  });

  it("shows one friendly toast for ACCOUNT_NOT_VERIFIED, however many calls fail", () => {
    wrap(as("PENDING_VERIFICATION"), <NotVerifiedListener />);
    window.dispatchEvent(new Event(NOT_VERIFIED_EVENT));
    window.dispatchEvent(new Event(NOT_VERIFIED_EVENT));
    return screen.findAllByTestId("toast").then((toasts) => {
      expect(toasts).toHaveLength(1);
      expect(toasts[0].textContent).toMatch(/not verified yet/);
      fireEvent.click(screen.getByRole("button", { name: "Close" }));
    });
  });
});

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/app" }));

describe("account block routing", () => {
  const fire = (code: string) => window.dispatchEvent(new CustomEvent(ACCOUNT_BLOCK_EVENT, { detail: code }));
  beforeEach(() => replace.mockClear());
  it("sends admins without TOTP to the security step", () => {
    wrap(as("PENDING_PROFILE", "ADMIN"), <NotVerifiedListener />);
    fire("MFA_REQUIRED");
    expect(replace).toHaveBeenCalledWith("/onboarding?step=security");
  });
  it("shows the suspended screen for a frozen business", () => {
    wrap(as("ACTIVE"), <NotVerifiedListener />);
    fire("ACCOUNT_SUSPENDED");
    expect(replace).toHaveBeenCalledWith("/account-status?reason=suspended");
  });
});
