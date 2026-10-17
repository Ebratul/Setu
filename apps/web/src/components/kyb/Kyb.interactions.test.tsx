import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import type { KybResult, SupplierListItem } from "@/lib/api/kyb";

const mocks = vi.hoisted(() => ({
  getSuppliers: vi.fn(),
  verifySupplier: vi.fn(),
}));

vi.mock("@/lib/api/kyb", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/kyb")>()),
  getSuppliers: mocks.getSuppliers,
  verifySupplier: mocks.verifySupplier,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/app/suppliers",
}));

import { RerunButton } from "./RerunButton";
import { SuppliersPage } from "./SuppliersPage";

const item = (over: Partial<SupplierListItem>): SupplierListItem => ({
  supplier_id: "id-x",
  code: "x",
  name: "X",
  city: "Ningbo",
  country: "CN",
  kyb_status: "VERIFIED",
  kyb_badge: "VERIFIED",
  kyb_score: 100,
  has_pending_change: false,
  last_checked: "2026-10-16T10:00:00Z",
  completed_deals: 3,
  your_deals_count: 2,
  on_time_rate_pct: "95.00",
  scorecard_score: "90.00",
  weak: false,
  ...over,
});

function wrap(ui: React.ReactNode) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
});

describe("SuppliersPage", () => {
  beforeEach(() => {
    mocks.getSuppliers.mockResolvedValue({
      suppliers: [
        item({ supplier_id: "a", code: "a", name: "Alpha Textile", city: "Shaoxing", has_pending_change: true }),
        item({ supplier_id: "b", code: "b", name: "Huameng Trading", city: "Guangzhou", kyb_badge: "WARNING", kyb_score: 40 }),
      ],
    });
  });

  it("lists suppliers, marks pending changes, filters and searches", async () => {
    wrap(<SuppliersPage />);
    expect(await screen.findAllByTestId("supplier-row")).toHaveLength(2);
    expect(screen.getAllByTestId("pending-marker")).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Check status"), { target: { value: "WARNING" } });
    expect(screen.getAllByTestId("supplier-row")).toHaveLength(1);
    expect(screen.getByText("Huameng Trading")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Check status"), { target: { value: "ALL" } });
    fireEvent.change(screen.getByLabelText("Search suppliers"), { target: { value: "shaoxing" } });
    expect(screen.getAllByTestId("supplier-row")).toHaveLength(1);
    expect(screen.getByText("Alpha Textile")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search suppliers"), { target: { value: "zzz" } });
    expect(screen.getByText("No supplier matches your filters.")).toBeInTheDocument();
  });
});

describe("RerunButton", () => {
  it("shows loading then reports the updated result", async () => {
    let resolve!: (r: KybResult) => void;
    mocks.verifySupplier.mockReturnValue(new Promise<KybResult>((r) => (resolve = r)));
    const onDone = vi.fn();
    wrap(<RerunButton supplierId="s1" onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: "Re-run KYB" }));
    expect(await screen.findByRole("button", { name: "Checking..." })).toBeDisabled();
    resolve({ status: "VERIFIED" } as KybResult);
    expect(await screen.findByText(/Result updated/)).toBeInTheDocument();
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("explains a 403", async () => {
    mocks.verifySupplier.mockRejectedValue(new ApiError(403, "forbidden"));
    wrap(<RerunButton supplierId="s1" onDone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Re-run KYB" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/cannot re-run/),
    );
  });
});
