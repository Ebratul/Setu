import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";

const api = vi.hoisted(() => ({ totpSetup: vi.fn(), totpEnable: vi.fn() }));
vi.mock("@/lib/api/account", () => api);
vi.mock("@/lib/qr", () => ({ qrPngDataUrl: () => Promise.resolve("data:image/png;base64,AAAA"), downloadHref: vi.fn() }));

import { TotpEnroll } from "./TotpEnroll";

beforeEach(() => {
  vi.clearAllMocks();
  setLang("en");
  api.totpSetup.mockResolvedValue({ otpauth_uri: "otpauth://totp/Setu:a@b.co?secret=JBSWY3DPEHPK3PXP", secret: "JBSWY3DPEHPK3PXP" });
});

describe("TotpEnroll", () => {
  it("shows the QR, the secret text fallback and the otpauth link", async () => {
    renderI18n(<TotpEnroll onComplete={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Start setup" }));
    expect(await screen.findByAltText("QR code for your authenticator app")).toBeTruthy();
    expect(screen.getByTestId("totp-secret").textContent).toBe("JBSW Y3DP EHPK 3PXP");
    fireEvent.click(screen.getByText("Show the setup link"));
    expect(screen.getByText(/otpauth:\/\/totp/)).toBeTruthy();
  });

  it("rejects a wrong code, then shows one-time recovery codes that must be confirmed", async () => {
    const done = vi.fn();
    api.totpEnable.mockRejectedValueOnce(new ApiError(400, "x", null, "TOTP_INVALID"));
    api.totpEnable.mockResolvedValueOnce({ recovery_codes: ["AAAA-1111", "BBBB-2222"] });
    renderI18n(<TotpEnroll onComplete={done} />);
    fireEvent.click(screen.getByRole("button", { name: "Start setup" }));
    const input = await screen.findByLabelText(/6-digit code/);
    fireEvent.change(input, { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Turn on two-factor authentication" }));
    expect(await screen.findByText(/That code is not correct/)).toBeTruthy();
    fireEvent.change(input, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Turn on two-factor authentication" }));
    expect(await screen.findByText("AAAA-1111")).toBeTruthy();
    const doneBtn = screen.getByRole("button", { name: "Done" });
    expect(doneBtn).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("I have saved these recovery codes."));
    expect(doneBtn).toHaveProperty("disabled", false);
    fireEvent.click(doneBtn);
    await waitFor(() => expect(done).toHaveBeenCalled());
  });
});
