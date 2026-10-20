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
let flags = { demoEnabled: false, googleEnabled: true };
const signInEmail = vi.fn();
const signInSocial = vi.fn();
const sendOtp = vi.fn();
vi.mock("@/lib/auth/client", () => ({
  getAuthMode: () => mode(),
  getPublicAuthConfig: async () => ({ mode: await mode(), ...flags }),
  getAuthClient: () => ({
    signIn: { email: signInEmail, social: signInSocial },
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
    flags = { demoEnabled: false, googleEnabled: true };
    signInSocial.mockResolvedValue({
      data: {
        url: "https://accounts.google.com/o/oauth2/auth",
        redirect: true,
      },
      error: null,
    });
    signInEmail.mockResolvedValue({ data: {}, error: null });
    sendOtp.mockResolvedValue({ data: {}, error: null });
  });

  it("shows the demo panel and warning in demo mode", async () => {
    mode.mockResolvedValue("demo");
    flags = { demoEnabled: true, googleEnabled: false };
    renderI18n(<LoginScreen />);
    expect(await screen.findByRole("note")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Demo accounts" })).toBeTruthy();
    expect(screen.queryByLabelText("Password")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Continue with Google" }),
    ).toBeNull();
  });

  it("hides the demo accounts when demo_enabled is false", async () => {
    mode.mockResolvedValue("neon");
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    expect(screen.queryByText("Demo accounts")).toBeNull();
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("shows the demo accounts next to Google when demo_enabled is true", async () => {
    mode.mockResolvedValue("neon");
    flags = { demoEnabled: true, googleEnabled: true };
    renderI18n(<LoginScreen />);
    expect(
      await screen.findByRole("heading", { name: "Demo accounts" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Continue with Google" }),
    ).toBeTruthy();
  });

  it("starts Google sign-in with a callback back to /login", async () => {
    mode.mockResolvedValue("neon");
    search = "next=%2Fapp%2Fdeals";
    const assign = vi.fn();
    vi.stubGlobal("location", {
      ...window.location,
      origin: "http://localhost:3000",
      assign,
    });
    renderI18n(<LoginScreen />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Continue with Google" }),
    );
    await waitFor(() => expect(signInSocial).toHaveBeenCalled());
    expect(signInSocial.mock.calls[0][0]).toEqual({
      provider: "google",
      callbackURL: "http://localhost:3000/login?oauth=1&next=%2Fapp%2Fdeals",
    });
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "https://accounts.google.com/o/oauth2/auth",
      ),
    );
    vi.unstubAllGlobals();
  });

  it("links to the explainer, terms and privacy", async () => {
    mode.mockResolvedValue("neon");
    renderI18n(<LoginScreen />);
    await screen.findByLabelText("Password");
    expect(
      screen
        .getByRole("link", { name: "Why we ask for business documents" })
        .getAttribute("href"),
    ).toBe("/docs/en/security/why-we-ask");
    expect(
      screen.getByRole("link", { name: "Terms" }).getAttribute("href"),
    ).toBe("/terms");
    expect(
      screen.getByRole("link", { name: "Privacy" }).getAttribute("href"),
    ).toBe("/privacy");
  });

  it.each([
    ["PENDING_PROFILE", "/onboarding"],
    ["PENDING_VERIFICATION", "/onboarding/status"],
    ["REJECTED", "/account-status?reason=rejected"],
    ["SUSPENDED", "/account-status?reason=suspended"],
  ])("finishes the Google return and routes %s", async (status, path) => {
    mode.mockResolvedValue("neon");
    search = "oauth=1";
    startSession.mockResolvedValue({ role: "BUYER", account_status: status });
    renderI18n(<LoginScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith(path));
  });

  it("sends an active buyer home after the Google return", async () => {
    mode.mockResolvedValue("neon");
    search = "oauth=1";
    startSession.mockResolvedValue({ role: "BUYER", account_status: "ACTIVE" });
    renderI18n(<LoginScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app"));
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
