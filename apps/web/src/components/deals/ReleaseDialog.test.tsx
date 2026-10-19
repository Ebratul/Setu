import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";
import { ApiError } from "@/lib/api/client";

import { risk } from "@/components/risk/fixtures";
import { ReleaseDialog } from "./DealActions";
import { deal, milestone } from "./fixtures";

const release = vi.fn();
vi.mock("@/lib/api/deals", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/deals")>()),
  releaseMilestone: (...a: unknown[]) => release(...a),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  release.mockReset();
});

function open(onDone = vi.fn(), onClose = vi.fn()) {
  render(
    <I18nProvider>
      <ToastProvider>
        <ReleaseDialog deal={deal()} milestone={milestone()} onDone={onDone} onClose={onClose} />
      </ToastProvider>
    </I18nProvider>,
  );
  return { onDone, onClose };
}

describe("ReleaseDialog", () => {
  it("is a labelled modal dialog stating the amount and Simulated", () => {
    open();
    const dialog = screen.getByRole("dialog", { name: "Release milestone 1?" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("$2,880.00");
    expect(dialog).toHaveTextContent("Simulated");
  });

  it("maps a stable error code to a friendly message", async () => {
    release.mockRejectedValue(new ApiError(409, "x", "raw server text", "EVIDENCE_NOT_VERIFIED"));
    open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("required documents are not verified yet");
    expect(alert).not.toHaveTextContent("raw server text");
  });

  it("sends one idempotency key per dialog, reused on retry", async () => {
    release.mockRejectedValueOnce(new ApiError(500, "x")).mockRejectedValueOnce(new ApiError(500, "x"));
    open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    await waitFor(() => expect(release).toHaveBeenCalledTimes(2));
    expect(release.mock.calls[0][1]).toBe(release.mock.calls[1][1]);
  });

  it("shows waiting-for-approval on a 202 PENDING_APPROVAL result", async () => {
    release.mockResolvedValue({ outcome: "PENDING_APPROVAL" });
    const { onDone } = open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    expect(await screen.findByTestId("pending-approval-note")).toHaveTextContent("Waiting for your approval");
    expect(onDone).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Open approvals" })).toBeInTheDocument();
  });

  it("shows the approval card with tier and reasons when risk requires approval", async () => {
    release.mockResolvedValue({ outcome: "PENDING_APPROVAL", risk: risk() });
    open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    const waiting = await screen.findByTestId("risk-waiting");
    expect(waiting).toHaveTextContent("Waiting for your approval (Tier 3): Amount above the Tier 1 limit");
    expect(screen.getByRole("link", { name: "Open approvals" })).toHaveAttribute("href", "/app/approvals");
  });

  it("shows the blocked card on a BLOCK decision", async () => {
    release.mockResolvedValue({ outcome: "PENDING_APPROVAL", risk: risk({ decision: "BLOCK" }) });
    open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    expect(await screen.findByTestId("risk-decision")).toHaveTextContent("Blocked");
  });

  it("toasts and closes on RELEASED", async () => {
    release.mockResolvedValue({ outcome: "RELEASED" });
    const { onClose } = open();
    fireEvent.click(screen.getByRole("button", { name: "Release payment" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(await screen.findByTestId("toast")).toHaveTextContent("Milestone released (simulated)");
  });
});
