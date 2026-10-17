import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { MilestoneStatus } from "@/lib/api/deals";

import { milestone } from "./fixtures";
import { MilestoneStepper } from "./MilestoneStepper";

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

function renderStepper(props: Parameters<typeof MilestoneStepper>[0]) {
  return render(
    <I18nProvider>
      <MilestoneStepper {...props} />
    </I18nProvider>,
  );
}

const CASES: [MilestoneStatus, string, string][] = [
  ["PENDING", "Locked", "◌"],
  ["READY", "Ready to release", "●"],
  ["PENDING_APPROVAL", "Waiting for approval", "◔"],
  ["RELEASED", "Released", "✓"],
  ["REFUNDED", "Refunded", "↩"],
  ["FROZEN", "Frozen", "■"],
];

describe("MilestoneStepper", () => {
  it.each(CASES)("%s shows text and icon, not colour alone", (status, text, icon) => {
    renderStepper({ milestones: [milestone({ status })], currency: "USD" });
    const badge = screen.getByTestId("milestone-status");
    expect(badge).toHaveTextContent(text);
    expect(badge).toHaveTextContent(icon);
    expect(screen.getByTestId("milestone")).toHaveAttribute("data-status", status);
  });

  it("is an ordered list and marks the open milestone as the current step", () => {
    renderStepper({
      currency: "USD",
      milestones: [
        milestone({ id: "a", seq: 1, status: "RELEASED" }),
        milestone({ id: "b", seq: 2, status: "READY" }),
        milestone({ id: "c", seq: 3, status: "PENDING" }),
      ],
    });
    const list = screen.getByRole("list", { name: "Milestones in order" });
    expect(list.tagName).toBe("OL");
    const items = within(list).getAllByTestId("milestone");
    expect(items[0]).not.toHaveAttribute("aria-current");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(items[2]).not.toHaveAttribute("aria-current");
  });

  it("lists required evidence with a status each, plus amount and percent", () => {
    renderStepper({ milestones: [milestone()], currency: "USD" });
    const items = screen.getAllByTestId("evidence-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Verified");
    expect(items[0]).toHaveTextContent("Proforma invoice");
    expect(items[1]).toHaveTextContent("Missing");
    expect(screen.getByText("$2,880.00")).toBeInTheDocument();
    expect(screen.getByText("(30%)")).toBeInTheDocument();
  });

  it("links a waiting approval to the approvals inbox", () => {
    renderStepper({ milestones: [milestone({ status: "PENDING_APPROVAL" })], currency: "USD" });
    expect(screen.getByTestId("waiting-approval")).toHaveTextContent("Waiting for your approval");
    expect(screen.getByRole("link", { name: "Open approvals" })).toHaveAttribute("href", "/app/approvals");
  });

  it("enables release from the server flag and calls back", () => {
    const onRelease = vi.fn();
    const m = milestone();
    renderStepper({ milestones: [m], currency: "USD", showRelease: true, onRelease });
    const btn = screen.getByRole("button", { name: "Release payment" });
    expect(btn).toBeEnabled();
    btn.click();
    expect(onRelease).toHaveBeenCalledWith(m);
  });

  it("disables release and shows the server reason when refused", () => {
    const reason = "Evidence is not verified yet";
    renderStepper({
      currency: "USD",
      showRelease: true,
      milestones: [
        milestone({
          status: "FROZEN",
          can: {
            can_release: { allowed: false, reason },
            can_refund: { allowed: false, reason: "x" },
          },
        }),
      ],
    });
    const btn = screen.getByRole("button", { name: "Release payment" });
    expect(btn).toBeDisabled();
    expect(screen.getByTestId("release-reason")).toHaveTextContent(reason);
    expect(btn).toHaveAttribute("aria-describedby", screen.getByTestId("release-reason").id);
  });

  it("hides release for settled milestones and for non-buyer views", () => {
    const { rerender } = renderStepper({
      milestones: [milestone({ status: "RELEASED" })],
      currency: "USD",
      showRelease: true,
    });
    expect(screen.queryByRole("button", { name: "Release payment" })).toBeNull();
    rerender(
      <I18nProvider>
        <MilestoneStepper milestones={[milestone()]} currency="USD" />
      </I18nProvider>,
    );
    expect(screen.queryByRole("button", { name: "Release payment" })).toBeNull();
  });
});
