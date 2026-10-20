import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "@/lib/api/auth";

import { Sidebar, SIDEBAR_KEY } from "./Sidebar";
import { renderI18n, setLang, user } from "./testUtils";

vi.mock("next/navigation", () => ({ usePathname: () => "/app/cashflow" }));
vi.mock("@/lib/api/auth", () => ({ getMe: vi.fn() }));
vi.mock("@/lib/api/approvals", () => ({
  APPROVALS_CHANGED: "approvals-changed",
  listApprovals: vi.fn().mockResolvedValue({ pending_count: 2, approvals: [] }),
}));

beforeEach(() => {
  localStorage.clear();
  setLang("en");
});

describe("Sidebar", () => {
  it("shows admin items only for staff", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    const { unmount } = renderI18n(<Sidebar />);
    await screen.findByRole("link", { name: /Dashboard/ });
    expect(screen.queryByRole("link", { name: "Attack console" })).toBeNull();
    expect(screen.getByRole("link", { name: "Scam simulator" })).toBeInTheDocument();
    unmount();

    vi.mocked(getMe).mockResolvedValue(user("ADMIN"));
    renderI18n(<Sidebar />);
    expect(await screen.findByRole("link", { name: "Attack console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registry" })).toBeInTheDocument();
  });

  it("marks the current page, keeps every main item, and shows the pending count", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    renderI18n(<Sidebar />);
    const cash = await screen.findByRole("link", { name: "Cash Flow" });
    expect(cash).toHaveAttribute("aria-current", "page");
    for (const name of ["Deals", "Financing", "Suppliers", "Analysis", "Documents", "Approvals", "Chat"]) {
      expect(screen.getByRole("link", { name: new RegExp(name) })).toBeInTheDocument();
    }
    expect(await screen.findByTestId("nav-pending-count")).toHaveTextContent("2");
  });

  it("persists the collapsed state", async () => {
    vi.mocked(getMe).mockResolvedValue(user("BUYER"));
    const { unmount } = renderI18n(<Sidebar />);
    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByTestId("sidebar")).toHaveAttribute("data-collapsed", "true");
    expect(localStorage.getItem(SIDEBAR_KEY)).toBe("collapsed");
    unmount();
    renderI18n(<Sidebar />);
    await waitFor(() => expect(screen.getByTestId("sidebar")).toHaveAttribute("data-collapsed", "true"));
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
  });
});
