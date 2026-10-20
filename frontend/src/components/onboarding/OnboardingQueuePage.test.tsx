import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang, user } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";
import { MeContext } from "@/lib/MeContext";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const listReviews = vi.fn();
const approveReview = vi.fn();
const rejectReview = vi.fn();
vi.mock("@/lib/api/onboarding", () => ({
  listReviews: (...a: unknown[]) => listReviews(...a),
  approveReview: (id: string) => approveReview(id),
  rejectReview: (id: string, r: string) => rejectReview(id, r),
}));

import { OnboardingQueuePage } from "./OnboardingQueuePage";

const review = (over: Record<string, unknown> = {}) => ({
  id: "r1",
  status: "PENDING",
  recommendation: "NEEDS_REVIEW",
  score: 42,
  user_id: "u1",
  user_email: "owner@acme.example",
  user_display_name: "Owner One",
  party: {
    id: "p1",
    kind: "BUYER",
    legal_name: "Acme Imports Ltd",
    license_name: null,
    license_no: "TL-1",
    tax_id: "123456789",
    city: "Dhaka",
    country: "BD",
    kyb_status: "PENDING",
  },
  bank_account: {
    bank_name: "Sample Bank",
    bank_country: "BD",
    account_masked: "****7890",
    holder_name: "Acme Imports Ltd",
    account_type: "CORPORATE",
    currency: "BDT",
    status: "PENDING_CHANGE",
  },
  checks: [
    { code: "TAX_ID_FORMAT", status: "PASS", detail: "ok" },
    { code: "SANCTIONS_SCREEN", status: "FAIL", detail: "name matched" },
  ],
  submitted_at: "2026-10-01T10:00:00Z",
  decided_at: null,
  decided_by: null,
  reason: null,
  ...over,
});

function renderAs(role: "ADMIN" | "BUYER" | "JUDGE") {
  return renderI18n(
    <MeContext.Provider value={user(role)}>
      <OnboardingQueuePage />
    </MeContext.Provider>,
  );
}

async function openFirst() {
  fireEvent.click((await screen.findAllByRole("button", { name: /Review: Acme Imports Ltd/ }))[0]);
  return screen.findByRole("heading", { level: 2, name: "Acme Imports Ltd" });
}

describe("OnboardingQueuePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setLang("en");
    listReviews.mockResolvedValue({ items: [review()] });
  });

  it("lists pending applications first and filters by tab", async () => {
    renderAs("ADMIN");
    expect((await screen.findAllByText("Acme Imports Ltd")).length).toBeGreaterThan(0);
    expect(listReviews.mock.calls[0][0]).toBe("PENDING");
    fireEvent.click(screen.getByRole("tab", { name: "All" }));
    await waitFor(() => expect(listReviews.mock.calls.at(-1)?.[0]).toBeUndefined());
    fireEvent.click(screen.getByRole("tab", { name: "Rejected" }));
    await waitFor(() => expect(listReviews.mock.calls.at(-1)?.[0]).toBe("REJECTED"));
  });

  it("shows facts, masked bank account and checks with severity text", async () => {
    renderAs("ADMIN");
    await openFirst();
    expect(screen.getByText("****7890")).toBeInTheDocument();
    expect(screen.getByText("Sanctions screening")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getAllByText("Needs review").length).toBeGreaterThan(0);
  });

  it("approves after confirmation and reloads", async () => {
    approveReview.mockResolvedValue(review({ status: "APPROVED" }));
    renderAs("ADMIN");
    await openFirst();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    expect(approveReview).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(approveReview).toHaveBeenCalledWith("r1"));
    expect(await screen.findByText("Acme Imports Ltd was approved.")).toBeInTheDocument();
    expect(listReviews.mock.calls.length).toBeGreaterThan(1);
  });

  it("requires a reason of at least 10 characters to reject", async () => {
    rejectReview.mockResolvedValue(review({ status: "REJECTED" }));
    renderAs("ADMIN");
    await openFirst();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Reject" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "too short" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "  Licence number not found  " } });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(rejectReview).toHaveBeenCalledWith("r1", "Licence number not found"));
  });

  it("shows SELF_DECISION and ONBOARDING_DECIDED errors inside the dialog", async () => {
    approveReview.mockRejectedValueOnce(new ApiError(403, "x", null, "SELF_DECISION"));
    approveReview.mockRejectedValueOnce(new ApiError(409, "x", null, "ONBOARDING_DECIDED"));
    renderAs("ADMIN");
    await openFirst();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You cannot decide your own application.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent(/already decided/));
  });

  it("shows a friendly no-access state to non-admins without calling the API", async () => {
    renderAs("BUYER");
    expect(await screen.findByText(/Only an administrator/)).toBeInTheDocument();
    expect(listReviews).not.toHaveBeenCalled();
  });

  it("shows the friendly 403 state when the server refuses", async () => {
    listReviews.mockRejectedValue(new ApiError(403, "x", null, "FORBIDDEN"));
    renderAs("JUDGE");
    expect(await screen.findByText(/permission|access/i)).toBeInTheDocument();
  });
});
