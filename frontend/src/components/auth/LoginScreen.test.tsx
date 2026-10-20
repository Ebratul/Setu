import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(search),
}));

const mode = vi.fn();
const signInEmail = vi.fn();
const sendOtp = vi.fn();
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => mode(),
  getAuthClient: () => ({
    signIn: { email: signInEmail },
    emailOtp: { sendVerificationOtp: sendOtp },
  }),
}));

const startSession = vi.fn();
const logout = vi.fn();
vi.mock("@/lib/api/auth", () => ({
  startSession: () => startSession(),
  logout: () => logout(),
  getDemoUsers: () => Promise.resolve({ users: [] }),
  demoLogin: vi.fn(),
}));
const endAuthSession = vi.fn();
vi.mock("@/lib/auth/flow", async (orig) => {
  const real = await orig<typeof import("@/lib/auth/flow")>();
  return { ...real, signOutEverywhere: vi.fn(async () => endAuthSession()) };
});

import { LoginScreen } from "./LoginScreen";

function fill() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.co" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw-123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}
const apiErr = (status: number, code: string) => new ApiError(status, "x", null, code);

describe("LoginScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    search = "";
    signInEmail.mockResolvedValue({ data: {}, error: null });
    sendOtp.mockResolvedValue({ data: {}, error: null });
  });

  it("shows the demo panel and warning in demo mode", async () => {
    mode.mockResolvedValue("demo");
    renderI18n(<LoginScreen />);
    expect(await screen.findByRole("note")).toBeTruthy();
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("shows the password form without the demo warning in neon mode", async () => {
    mode.mockResolvedValue("neon");
    renderI18n(<LoginScreen />);
    expect(await screen.findByLabelText("Password")).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.getByRole("link", { name: "Forgot your password?" }).getAttribute("href")).toBe("/forgot-password");
    expect(screen.getByRole("link", { name: "Create a sign-in" }).getAttribute("href")).toBe("/register");
  });

  it("routes by role after sign-in", async () => {
    mode.mockResolvedValue("neon");
    startSession.mockResolvedValue({ role: "SUPPLIER" });
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    fill();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/supplier"));
  });

  it("shows invalid credentials", async () => {
    mode.mockResolvedValue("neon");
    signInEmail.mockResolvedValue({ data: null, error: { code: "invalid_credentials", status: 401 } });
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    fill();
    expect((await screen.findByRole("alert")).textContent).toMatch(/not correct/);
    expect(startSession).not.toHaveBeenCalled();
  });

  it("sends an unverified user to the verify step", async () => {
    mode.mockResolvedValue("neon");
    signInEmail.mockRejectedValue({ code: "email_not_confirmed", status: 403, message: "x" });
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    fill();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/verify-email?email=a%40b.co"));
    expect(sendOtp).toHaveBeenCalled();
  });

  it.each([
    ["ACCOUNT_NOT_ONBOARDED", "/onboarding"],
    ["ACCOUNT_PENDING", "/onboarding/status"],
    ["ACCOUNT_SUSPENDED", "/account-status?reason=suspended"],
  ])("routes %s to its screen", async (code, path) => {
    mode.mockResolvedValue("neon");
    startSession.mockRejectedValue(apiErr(403, code));
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    fill();
    await waitFor(() => expect(replace).toHaveBeenCalledWith(path));
  });

  it("signs out and shows a message on TOKEN_INVALID", async () => {
    mode.mockResolvedValue("neon");
    startSession.mockRejectedValue(apiErr(401, "TOKEN_INVALID"));
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    fill();
    expect((await screen.findByRole("alert")).textContent).toMatch(/session could not be confirmed/);
    expect(endAuthSession).toHaveBeenCalled();
  });
});
