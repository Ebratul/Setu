import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";
import type { Approval } from "@/lib/api/approvals";

import { ApprovalCard } from "./ApprovalCard";

const approve = vi.fn();
const reject = vi.fn();
vi.mock("@/lib/api/approvals", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/approvals")>()),
  approve: (...a: unknown[]) => approve(...a),
  reject: (...a: unknown[]) => reject(...a),
  getApproval: vi.fn(),
}));

const base: Approval = {
  id: "a1",
  action: "RELEASE_MILESTONE",
  action_label_en: "Change the supplier's receiving account",
  action_label_bn: "বদল",
  what_happens_en: "Pays the NEW account from now on.",
  what_happens_bn: "নতুন অ্যাকাউন্ট",
  tier: 2,
  status: "APPROVED",
  deal_id: "d1",
  deal_reference: "SETU-2026-0001",
  supplier_name: "Huaxin",
  milestone_seq: null,
  amount: null,
  currency: null,
  reasons: [
    {
      code: "NEW_ACCOUNT",
      message: "Account first seen 1 day ago.",
      message_bn: "বাংলা",
    },
  ],
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
  why_pause_en:
    "This pause protects you from rushed payment-redirection scams.",
  why_pause_bn: "বিরতি",
  evidence: null,
  simulated: true,
};

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  approve.mockReset();
  reject.mockReset();
});

function show(a: Approval) {
  render(
    <I18nProvider>
      <ToastProvider>
        <ApprovalCard
          approval={a}
          fetchedAt={Date.now()}
          now={Date.now()}
          onReview={vi.fn()}
        />
      </ToastProvider>
    </I18nProvider>,
  );
}

describe("approved but not carried out", () => {
  it("offers to run it again and calls approve without a code", async () => {
    approve.mockResolvedValue({
      outcome: "EXECUTED",
      message_en: "Done.",
      message_bn: "",
    });
    show(base);
    expect(screen.queryByTestId("review-btn")).toBeNull();
    fireEvent.click(screen.getByTestId("run-approved-btn"));
    await waitFor(() => expect(approve).toHaveBeenCalledWith("a1"));
    expect(await screen.findByText("Done.")).toBeInTheDocument();
  });

  it("has no run button once it was carried out", () => {
    show({ ...base, status: "EXECUTED" });
    expect(screen.queryByTestId("run-approved-btn")).toBeNull();
  });

  it("lets the buyer reject it instead", async () => {
    reject.mockResolvedValue({ approval: { ...base, status: "REJECTED" } });
    show(base);
    fireEvent.click(screen.getByTestId("reject-approved-btn"));
    await waitFor(() => expect(reject).toHaveBeenCalledWith("a1"));
    expect(approve).not.toHaveBeenCalled();
  });

  it("shows the friendly text when the payment was already posted", async () => {
    const { ApiError } = await import("@/lib/api/client");
    approve.mockRejectedValue(
      new ApiError(409, "Conflict", "x", "RELEASE_ALREADY_POSTED"),
    );
    show(base);
    fireEvent.click(screen.getByTestId("run-approved-btn"));
    expect(
      await screen.findByText(/already posted earlier/),
    ).toBeInTheDocument();
  });
});
