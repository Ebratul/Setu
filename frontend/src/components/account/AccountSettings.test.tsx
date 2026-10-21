import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { ToastProvider } from "@/components/ui/Toast";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const api = vi.hoisted(() => ({
  getAccount: vi.fn(),
  patchAccount: vi.fn(),
  exportAccount: vi.fn(),
  requestDeletion: vi.fn(),
  totpSetup: vi.fn(),
  totpEnable: vi.fn(),
  totpDisable: vi.fn(),
  totpRegenerate: vi.fn(),
}));
vi.mock("@/lib/api/account", () => api);
const sdk = vi.hoisted(() => ({
  listSessions: vi.fn(),
  getSession: vi.fn(),
  revokeSession: vi.fn(),
  revokeOtherSessions: vi.fn(),
  revokeSessions: vi.fn(),
  listAccounts: vi.fn(),
}));
const revoked = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/auth", () => ({ recordSessionRevoked: revoked }));
vi.mock("@/lib/auth/client", () => ({ getAuthMode: () => Promise.resolve("neon"), getAuthClient: () => sdk }));
const signOut = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/flow", async (orig) => ({ ...(await orig<typeof import("@/lib/auth/flow")>()), signOutEverywhere: signOut }));
vi.mock("@/lib/qr", () => ({ qrPngDataUrl: () => Promise.resolve("data:,"), downloadHref: vi.fn() }));

import { AccountSettings } from "./AccountSettings";

const account = { display_name: "Rahim", email: "r@example.com", role: "BUYER", language: "en", mobile_masked: "01*******78", auth_provider: "neon", mfa_enabled: true, terms_version: "2026-10" };
const mount = () => renderI18n(<ToastProvider><AccountSettings /></ToastProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  setLang("en");
  api.getAccount.mockResolvedValue(account);
  sdk.listSessions.mockResolvedValue({ data: [{ token: "t1", userAgent: "Firefox", ipAddress: "1.2.3.4" }, { token: "t2", userAgent: "Chrome on phone" }], error: null });
  sdk.getSession.mockResolvedValue({ data: { session: { token: "t1" } }, error: null });
  sdk.listAccounts.mockResolvedValue({ data: [{ providerId: "google" }] });
  revoked.mockResolvedValue(undefined);
  sdk.revokeSession.mockResolvedValue({ data: {}, error: null });
  sdk.revokeOtherSessions.mockResolvedValue({ data: {}, error: null });
  sdk.revokeSessions.mockResolvedValue({ data: {}, error: null });
});

describe("AccountSettings", () => {
  it("shows the profile, the linked Google account and the sessions with the current one marked", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "Account settings", level: 1 })).toBeTruthy();
    expect(await screen.findByText("Google account")).toBeTruthy();
    expect(screen.getByText("01*******78")).toBeTruthy();
    expect(await screen.findByText("This device")).toBeTruthy();
    expect(screen.getByText("Chrome on phone")).toBeTruthy();
  });

  it("signs out another session and all other devices", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Sign out: Chrome on phone/ }));
    await waitFor(() => expect(sdk.revokeSession).toHaveBeenCalledWith({ token: "t2" }));
    await waitFor(() => expect(revoked).toHaveBeenCalledWith("one"));
    fireEvent.click(screen.getByRole("button", { name: "Sign out other devices" }));
    await waitFor(() => expect(sdk.revokeOtherSessions).toHaveBeenCalled());
    await waitFor(() => expect(revoked).toHaveBeenCalledWith("others"));
  });

  it("signs out everywhere and returns to the login page", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Sign out everywhere" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(sdk.revokeSessions).toHaveBeenCalled();
    expect(revoked).toHaveBeenCalledWith("all");
    expect(signOut).toHaveBeenCalled();
  });

  it("disables turning off 2FA for administrators", async () => {
    api.getAccount.mockResolvedValue({ ...account, role: "ADMIN" });
    mount();
    const off = await screen.findByRole("button", { name: "Turn off two-factor authentication" });
    expect(off).toHaveProperty("disabled", true);
    expect(screen.getByText(/Administrators cannot turn off/)).toBeTruthy();
  });

  it("turns 2FA off with a code and regenerates recovery codes", async () => {
    api.totpDisable.mockResolvedValue(undefined);
    api.totpRegenerate.mockResolvedValue({ recovery_codes: ["NEW-1111"] });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Regenerate recovery codes" }));
    let dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/6-digit code/), { target: { value: "123456" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Regenerate" }));
    expect(await screen.findByText("NEW-1111")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("I have saved these recovery codes."));
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    fireEvent.click(await screen.findByRole("button", { name: "Turn off two-factor authentication" }));
    dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/6-digit code/), { target: { value: "654321" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(api.totpDisable).toHaveBeenCalledWith("654321"));
  });

  it("asks for confirmation before requesting deletion, then signs out", async () => {
    api.requestDeletion.mockResolvedValue(undefined);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Request account deletion" }));
    const dialog = await screen.findByRole("dialog");
    expect(api.requestDeletion).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Request deletion" }));
    await waitFor(() => expect(api.requestDeletion).toHaveBeenCalled());
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  it("downloads the user's data", async () => {
    api.exportAccount.mockResolvedValue({ email: "r@example.com" });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Download my data" }));
    await waitFor(() => expect(api.exportAccount).toHaveBeenCalled());
  });
});
