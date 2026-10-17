import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import type { RegistryEntry } from "@/lib/api/registry";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/registry", async (orig) => {
  const real = await orig<typeof import("@/lib/api/registry")>();
  return { ...real, listRegistry: vi.fn(), getRegistryStats: vi.fn() };
});
import * as api from "@/lib/api/registry";

import { RegistryAdminPage } from "./RegistryAdminPage";

const entry = (over: Partial<RegistryEntry> = {}): RegistryEntry => ({
  id: "e1",
  sha256_prefix: "ab12cd34ef56",
  semantic_prefix: null,
  doc_type: "PROFORMA_INVOICE",
  purpose: "FINANCING_COLLATERAL",
  lender_name: "Lender A",
  deal_ref: "SETU-2026-0001",
  registered_on: "2026-10-01",
  last_seen_at: null,
  seen_count: 3,
  exact_hits: 2,
  near_hits: 1,
  status: "ACTIVE",
  ...over,
});

const wrap = () =>
  render(
    <I18nProvider>
      <RegistryAdminPage />
    </I18nProvider>,
  );

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
  vi.mocked(api.getRegistryStats).mockResolvedValue({
    entries: 5, active: 4, released: 1, by_purpose: {}, duplicates_blocked: 3, exact_blocked: 2, near_blocked: 1,
  });
  vi.mocked(api.listRegistry).mockResolvedValue({ items: [entry()], total: 1 });
});

describe("RegistryAdminPage", () => {
  it("renders counters and the entry row with icon+text badges", async () => {
    wrap();
    const row = await screen.findByTestId("registry-row");
    expect(within(row).getByText("ab12cd34ef56")).toHaveClass("font-mono");
    expect(within(row).getByText("Lender A")).toBeInTheDocument();
    expect(within(row).getByText("Financing collateral")).toBeInTheDocument();
    expect(within(row).getByText("2 / 1")).toBeInTheDocument();
    expect(within(row).getByText("Active")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("duplicates-total")).toHaveTextContent("3"));
    expect(screen.getByTestId("exact-total")).toHaveTextContent("2");
    expect(screen.getByTestId("near-total")).toHaveTextContent("1");
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
  });

  it("filters by status and result and resets to the first page", async () => {
    wrap();
    await screen.findByTestId("registry-row");
    fireEvent.click(screen.getByLabelText("Released"));
    await waitFor(() =>
      expect(api.listRegistry).toHaveBeenLastCalledWith(expect.objectContaining({ status: "RELEASED", offset: 0 }), expect.anything()),
    );
    fireEvent.click(screen.getByLabelText("Near"));
    await waitFor(() =>
      expect(api.listRegistry).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "RELEASED", result: "NEAR_DUPLICATE" }),
        expect.anything(),
      ),
    );
  });

  it("paginates with limit/offset", async () => {
    vi.mocked(api.listRegistry).mockResolvedValue({ items: [entry()], total: 45 });
    wrap();
    await screen.findByTestId("registry-row");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(api.listRegistry).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 20, offset: 20 }), expect.anything()),
    );
  });

  it("shows the empty state", async () => {
    vi.mocked(api.listRegistry).mockResolvedValue({ items: [], total: 0 });
    wrap();
    expect(await screen.findByText(/No registry entries match/)).toBeInTheDocument();
  });

  it("shows the no-access pattern on 403", async () => {
    vi.mocked(api.getRegistryStats).mockRejectedValue(new ApiError(403, "x"));
    vi.mocked(api.listRegistry).mockRejectedValue(new ApiError(403, "x"));
    wrap();
    expect((await screen.findAllByText("You do not have access to this page")).length).toBeGreaterThan(0);
  });
});
