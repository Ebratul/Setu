import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";
import type { Approval } from "@/lib/api/approvals";
import { ApiError } from "@/lib/api/client";

import { ApprovalDialog } from "./ApprovalDialog";

const getApproval = vi.fn();
const approve = vi.fn();
const reject = vi.fn();
vi.mock("@/lib/api/approvals", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/approvals")>()),
  getApproval: (...a: unknown[]) => getApproval(...a),
  approve: (...a: unknown[]) => approve(...a),
  reject: (...a: unknown[]) => reject(...a),
  resendOtp: vi.fn(),
  cancelApproval: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const base: Approval = {
  id: "a1",
  action: "CHANGE_BENEFICIARY",
  action_label_en: "Change the supplier's receiving account",
  action_label_bn: "বদল",
  what_happens_en: "Pays the NEW account from now on.",
  what_happens_bn: "নতুন অ্যাকাউন্ট",
  tier: 3,
  status: "PENDING",
  deal_id: "d1",
  deal_reference: "SETU-2026-0001",
  supplier_name: "Huaxin",
  milestone_seq: null,
  amount: null,
  currency: null,
  reasons: [{ code: "NEW_ACCOUNT", message: "Account first seen 1 day ago.", message_bn: "বাংলা" }],
  requested_by: "supplier",
  requested_via: "portal",
  otp_required: true,
  created_at: "2026-10-20T00:00:00Z",
  expires_at: null,
  cooling_off_until: "2026-10-20T00:10:00Z",
  seconds_to_cooling_off_end: 2,
  cooling_off_total_seconds: 600,
  otp_attempts_left: 3,
  otp_sent: true,
  decided_at: null,
  decision_note: null,
  can_approve: true,
  can_reject: true,
  can_cancel: true,
  blocked_reason: null,
  why_pause_en: "This pause protects you from rushed payment-redirection scams.",
  why_pause_bn: "বিরতি",
  evidence: null,
  simulated: true,
};

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  getApproval.mockReset();
  approve.mockReset();
  reject.mockReset();
});

function show(a: Approval) {
  getApproval.mockResolvedValue({ value: a, at: Date.now() });
  render(
    <I18nProvider>
      <ToastProvider>
        <ApprovalDialog id={a.id} onClose={vi.fn()} onChanged={vi.fn()} />
      </ToastProvider>
    </I18nProvider>,
  );
}
const typeCode = (code: string) => {
  const first = screen.getByLabelText("Digit 1 of 6");
  fireEvent.paste(first, { clipboardData: { getData: () => code } });
};

describe("Tier 3 dialog", () => {
  it("keeps Approve disabled until the cooling-off ends and six digits are entered", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    show(base);
    await screen.findByTestId("tier3-dialog");
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("This pause protects you from rushed payment-redirection scams.");
    const approveBtn = screen.getByTestId("approve-btn");
    typeCode("123456");
    expect(approveBtn).toBeDisabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(screen.getByTestId("cooling-ring")).toHaveAttribute("data-done", "true");
    expect(approveBtn).toBeEnabled();
    fireEvent.paste(screen.getByLabelText("Digit 1 of 6"), { clipboardData: { getData: () => "12" } });
    await waitFor(() => expect(approveBtn).toBeDisabled());
    vi.useRealTimers();
  });

  it("shows tries left after a wrong code and a locked alert after OTP_LOCKED", async () => {
    show({ ...base, seconds_to_cooling_off_end: 0 });
    await screen.findByTestId("tier3-dialog");
    typeCode("111111");
    approve.mockRejectedValueOnce(new ApiError(422, "x", "wrong code, 2 tries left", "OTP_INVALID"));
    fireEvent.click(screen.getByTestId("approve-btn"));
    expect(await screen.findByText("Wrong code. 2 tries left.")).toBeInTheDocument();

    typeCode("222222");
    approve.mockRejectedValueOnce(new ApiError(409, "x", "locked", "OTP_LOCKED"));
    fireEvent.click(screen.getByTestId("approve-btn"));
    const locked = await screen.findByTestId("otp-locked");
    expect(locked).toHaveAttribute("role", "alert");
    expect(screen.getByTestId("approve-btn")).toBeDisabled();
  });

  it("disables Approve for an email-origin request and keeps Reject", async () => {
    show({ ...base, requested_via: "email", blocked_reason: "EMAIL_ORIGIN", can_approve: false });
    await screen.findByTestId("tier3-dialog");
    expect(screen.getByTestId("email-origin-note")).toHaveTextContent("Setu never changes accounts from email");
    expect(screen.getByTestId("approve-btn")).toBeDisabled();
    expect(screen.getByTestId("reject-btn")).toBeEnabled();
    expect(screen.queryByTestId("otp-input")).toBeNull();
  });
});

describe("Tier 2 dialog", () => {
  const t2: Approval = {
    ...base,
    id: "a2",
    tier: 2,
    action: "RELEASE_MILESTONE",
    action_label_en: "Release a payment tranche",
    amount: "2880.00",
    currency: "USD",
    otp_required: false,
    cooling_off_until: null,
    seconds_to_cooling_off_end: null,
    cooling_off_total_seconds: null,
    can_cancel: false,
    why_pause_en: null,
    why_pause_bn: null,
  };

  it("approves in one tap and shows Simulated", async () => {
    show(t2);
    await screen.findByTestId("tier2-dialog");
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Simulated");
    expect(dialog).toHaveTextContent("$2,880.00");
    expect(screen.queryByTestId("otp-input")).toBeNull();
    approve.mockResolvedValue({ outcome: "EXECUTED", approval: t2, new_approval: null, message_en: "Done", message_bn: "", context_changed: false });
    fireEvent.click(screen.getByTestId("approve-btn"));
    await waitFor(() => expect(approve).toHaveBeenCalledWith("a2", undefined));
  });

  it("switches to the Tier 3 request when the engine re-escalates", async () => {
    show(t2);
    await screen.findByTestId("tier2-dialog");
    getApproval.mockResolvedValue({ value: { ...base, id: "a3" }, at: Date.now() });
    approve.mockResolvedValue({
      outcome: "RE_ESCALATED",
      approval: t2,
      new_approval: { ...base, id: "a3" },
      message_en: "Conditions changed: now Tier 3.",
      message_bn: "",
      context_changed: true,
    });
    fireEvent.click(screen.getByTestId("approve-btn"));
    expect(await screen.findByTestId("reescalated-note")).toHaveTextContent("Conditions changed: now Tier 3.");
    expect(await screen.findByTestId("otp-input")).toBeInTheDocument();
  });
});
