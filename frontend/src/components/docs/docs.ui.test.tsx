import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InfoTip } from "./InfoTip";
import { PageFeedback } from "./PageFeedback";

vi.mock("next/navigation", () => ({ usePathname: () => "/app/approvals", useRouter: () => ({ push: vi.fn() }) }));

describe("InfoTip", () => {
  it("opens a one-line explanation with a link to the guide anchor and closes on Escape", () => {
    render(<InfoTip topic="tier" doc="security/permission-tiers#what-it-is" />);
    const btn = screen.getByTestId("info-tip-tier");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(screen.getByRole("note")).toHaveTextContent(/tier/i);
    expect(screen.getByRole("link")).toHaveAttribute("href", "/docs/en/security/permission-tiers#what-it-is");
    fireEvent.keyDown(btn, { key: "Escape" });
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("PageFeedback", () => {
  it("stores a vote per page and shows thanks", () => {
    localStorage.clear();
    render(<PageFeedback pageId="en:buyer/approvals" />);
    fireEvent.click(screen.getByTestId("docs-vote-no"));
    fireEvent.change(screen.getByLabelText(/tell us more/i), { target: { value: "unclear" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.getByRole("status")).toHaveTextContent(/thank you/i);
    expect(JSON.parse(localStorage.getItem("setu_docs_feedback:en:buyer/approvals") ?? "{}")).toMatchObject({ vote: "no", comment: "unclear" });
  });
});
