import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";

import { NewDealPage } from "./NewDealPage";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/kyb", () => ({
  getSuppliers: vi.fn().mockResolvedValue({
    suppliers: [
      { supplier_id: "s-ok", name: "Good Co", city: "Ningbo", country: "CN", kyb_badge: "VERIFIED" },
      { supplier_id: "s-warn", name: "Risky Co", city: "Guangzhou", country: "CN", kyb_badge: "WARNING" },
    ],
  }),
}));
vi.mock("@/lib/api/analysis", () => ({
  postLandedCost: vi.fn().mockResolvedValue({
    currency: "USD",
    landed_cost: { USD: "10450.00", BDT: "1", CNY: "1" },
    cost_per_unit: { USD: "1.31", BDT: "1", CNY: "1" },
  }),
}));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

function renderPage() {
  return render(
    <I18nProvider>
      <ToastProvider>
        <NewDealPage />
      </ToastProvider>
    </I18nProvider>,
  );
}

async function toGoods() {
  renderPage();
  fireEvent.click(await screen.findByLabelText(/Good Co/));
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
}

describe("NewDealPage", () => {
  it("shows an exact live total as quantity times unit price (no float drift)", async () => {
    await toGoods();
    const total = screen.getByTestId("goods-total");
    expect(total).toHaveTextContent("—");
    fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Unit price"), { target: { value: "0.1" } });
    expect(total).toHaveTextContent("$0.30");
    fireEvent.change(screen.getByLabelText("Quantity"), { target: { value: "8000" } });
    fireEvent.change(screen.getByLabelText("Unit price"), { target: { value: "1.20" } });
    expect(total).toHaveTextContent("$9,600.00");
  });

  it("blocks the step with linked errors until the goods are valid", async () => {
    await toGoods();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    const qty = screen.getByLabelText("Quantity");
    expect(qty).toHaveAttribute("aria-invalid", "true");
    expect(qty).toHaveAccessibleDescription("Enter a number above zero.");
    expect(screen.getByRole("heading", { name: "What are you buying?" })).toBeInTheDocument();
  });

  it("asks for confirmation before choosing a supplier with a warning", async () => {
    renderPage();
    fireEvent.click(await screen.findByLabelText(/Risky Co/));
    const dialog = screen.getByRole("dialog", { name: "Risky Co has a warning" });
    expect(dialog).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use this supplier anyway" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByLabelText(/Risky Co/)).toBeChecked();
  });
});
