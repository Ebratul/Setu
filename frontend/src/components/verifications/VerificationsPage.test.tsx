import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderI18n, setLang, user } from "@/components/shell/testUtils";
import { ApiError } from "@/lib/api/client";
import { MeContext } from "@/lib/MeContext";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
const api = vi.hoisted(() => ({
  listReviews: vi.fn(),
  getReview: vi.fn(),
  revealField: vi.fn(),
  getOnboardingState: vi.fn(),
  documentUrl: vi.fn(),
  approveReview: vi.fn(),
  requestChanges: vi.fn(),
  rejectReview: vi.fn(),
  suspendReview: vi.fn(),
  autoApproveReview: vi.fn(),
}));
vi.mock("@/lib/api/onboarding", () => api);
const stepup = vi.hoisted(() => ({ startStepup: vi.fn(), verifyStepup: vi.fn() }));
vi.mock("@/lib/api/auth", () => stepup);

import { VerificationsPage } from "./VerificationsPage";

const item = {
  id: "r1",
  status: "PENDING",
  role: "SUPPLIER",
  account_status: "PENDING_VERIFICATION",
  decision: null,
  recommendation: "NEEDS_REVIEW",
  score: 60,
  user_id: "u-other",
  user_email: "li@example.com",
  user_display_name: "Li Wei",
  party: { legal_name: "Shenzhen Bright Co" },
  contact: { mobile_masked: "+86*******78" },
  submitted_at: "2026-10-20T10:00:00Z",
};
const detail = (over = {}) => ({
  ...item,
  business: { legal_name_en: "Shenzhen Bright Co", uscc_masked: "**************Y43", bank: { account_masked: "****7890" } },
  documents: [{ id: "d1", type: "BUSINESS_LICENSE", original_name: "licence.pdf", mime: "application/pdf", size: 10, status: "UPLOADED", created_at: "x" }],
  checks: [
    { code: "DOC_PRESENT", status: "PASS", detail: "ok" },
    { code: "DUPLICATE_COMPANY", status: "WARN", detail: "needs manual review" },
  ],
  change_requests: [],
  decided_at: null,
  reason: null,
  ...over,
});

function mount(role: "ADMIN" | "BUYER" = "ADMIN") {
  return renderI18n(
    <MeContext.Provider value={user(role) as never}>
      <VerificationsPage />
    </MeContext.Provider>,
  );
}

async function open() {
  fireEvent.click((await screen.findAllByRole("button", { name: /Review: Shenzhen Bright Co/ }))[0]);
  await screen.findByRole("heading", { name: "Shenzhen Bright Co", level: 2 });
}

beforeEach(() => {
  vi.clearAllMocks();
  setLang("en");
  api.listReviews.mockResolvedValue({ items: [item] });
  api.getReview.mockResolvedValue(detail());
  api.getOnboardingState.mockResolvedValue({ demo_mode: false });
});

describe("VerificationsPage", () => {
  it("blocks non-admins", async () => {
    mount("BUYER");
    expect(await screen.findByText(/Only an administrator/)).toBeTruthy();
    expect(api.listReviews).not.toHaveBeenCalled();
  });

  it("lists applications and shows masked fields and checks with text status", async () => {
    mount();
    await open();
    expect(screen.getByText("**************Y43")).toBeTruthy();
    expect(screen.getByText("Needs attention")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Auto-approve (demo)" })).toBeNull();
  });

  it("reveals a value only with a reason of at least 10 characters", async () => {
    api.revealField.mockResolvedValue({ field: "uscc", value: "91350100M000100Y43" });
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: /Reveal: Unified Social Credit Code/ }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Reveal" });
    expect(confirm).toHaveProperty("disabled", true);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "too short" } });
    expect(confirm).toHaveProperty("disabled", true);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Matching against the licence scan" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(api.revealField).toHaveBeenCalledWith("r1", "uscc", "Matching against the licence scan"));
    expect(await screen.findByText("91350100M000100Y43")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Hide: Unified Social Credit Code/ }));
    expect(screen.queryByText("91350100M000100Y43")).toBeNull();
  });

  it("approves after confirming", async () => {
    api.approveReview.mockResolvedValue(detail({ status: "APPROVED" }));
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(api.approveReview).toHaveBeenCalledWith("r1", null));
    expect(await screen.findByText("Shenzhen Bright Co was approved.")).toBeTruthy();
  });

  it("requires a reason to reject or suspend", async () => {
    api.rejectReview.mockResolvedValue(detail());
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    const dialog = await screen.findByRole("dialog");
    const go = within(dialog).getByRole("button", { name: "Reject" });
    expect(go).toHaveProperty("disabled", true);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Licence does not match" } });
    fireEvent.click(go);
    await waitFor(() => expect(api.rejectReview).toHaveBeenCalledWith("r1", "Licence does not match", null));
  });

  it("requests changes for chosen fields and documents with a note each", async () => {
    api.requestChanges.mockResolvedValue(detail());
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Request changes" }));
    const dialog = await screen.findByRole("dialog");
    const send = within(dialog).getByRole("button", { name: "Send request" });
    expect(send).toHaveProperty("disabled", true);
    fireEvent.click(within(dialog).getByLabelText("Business licence"));
    fireEvent.change(within(dialog).getByLabelText(/Note for: Business licence/), { target: { value: "Scan is cropped" } });
    fireEvent.click(send);
    await waitFor(() => expect(api.requestChanges).toHaveBeenCalledWith("r1", [{ target: "BUSINESS_LICENSE", note: "Scan is cropped" }], null));
  });

  it("asks for a fresh authenticator code when the API wants a step-up, then retries", async () => {
    api.suspendReview.mockRejectedValueOnce(new ApiError(403, "x", null, "STEPUP_TOTP_REQUIRED"));
    api.suspendReview.mockResolvedValueOnce(detail());
    stepup.verifyStepup.mockResolvedValue({ token: "STEP1", expires_in_seconds: 600, header: "X-Stepup" });
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));
    const reason = within(await screen.findByRole("dialog")).getByLabelText(/Reason/);
    fireEvent.change(reason, { target: { value: "Fraud indicators found" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Suspend" }));
    const step = await screen.findByRole("heading", { name: "Confirm with a security code" });
    expect(step).toBeTruthy();
    const dialogs = screen.getAllByRole("dialog");
    const top = dialogs[dialogs.length - 1];
    expect(within(top).queryByRole("button", { name: /Email me/ })).toBeNull();
    fireEvent.change(within(top).getByLabelText(/Authenticator or recovery code/), { target: { value: "ABCDE-FGHJK" } });
    fireEvent.click(within(top).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(stepup.verifyStepup).toHaveBeenCalledWith("ABCDE-FGHJK"));
    await waitFor(() => expect(api.suspendReview).toHaveBeenLastCalledWith("r1", "Fraud indicators found", "STEP1"));
  });

  it("shows Auto-approve only when the API says demo mode, and disables decisions on your own account", async () => {
    api.getOnboardingState.mockResolvedValue({ demo_mode: true });
    mount();
    await open();
    expect(screen.getByRole("button", { name: "Auto-approve (demo)" })).toBeTruthy();
  });

  it("disables every decision on the admin's own application", async () => {
    api.getReview.mockResolvedValue(detail({ user_id: "u-ADMIN" }));
    mount();
    await open();
    expect(screen.getByText("You cannot decide your own account.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve" })).toHaveProperty("disabled", true);
  });

  it.each([
    ["SANCTIONS_BLOCK", /matched a screening list/],
    ["DUPLICATE_COMPANY_APPROVED", /already approved/],
  ])("shows a friendly message for %s on approve", async (code, text) => {
    api.approveReview.mockRejectedValue(new ApiError(409, "x", null, code));
    mount();
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(text);
  });
});
