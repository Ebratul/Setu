import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { deal } from "@/components/deals/fixtures";
import { ToastProvider } from "@/components/ui/Toast";
import { I18nProvider } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import type { PaymentOut } from "@/lib/api/payments";

import { PaypalCheckout } from "./PaypalCheckout";
import type { PaypalButtonsConfig } from "./paypalSdk";

const api = vi.hoisted(() => ({
  getPaypalConfig: vi.fn(),
  createPaypalOrder: vi.fn(),
  capturePaypalOrder: vi.fn(),
  cancelPaypalOrder: vi.fn(),
  listDealPayments: vi.fn(),
  fundEscrowFromPayment: vi.fn(),
}));
vi.mock("@/lib/api/payments", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/payments")>()),
  ...api,
}));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

let cfg: PaypalButtonsConfig;

function payment(over: Partial<PaymentOut> = {}): PaymentOut {
  return {
    simulated: true,
    provider: "PAYPAL_SANDBOX",
    id: "pay-1",
    deal_id: "d1",
    deal_reference: "SETU-2026-0001",
    coverage: "NEXT_TRANCHE",
    status: "CREATED",
    amount: "2880.00",
    currency: "USD",
    charge_amount: "2880.00",
    charge_currency: "USD",
    fx_rate: null,
    provider_order_id: "ORDER-1",
    provider_capture_id: null,
    provider_status: null,
    failure_code: null,
    created_at: "2026-10-20T10:00:00Z",
    captured_at: null,
    escrow_funded_at: null,
    funding_approval_id: null,
    can_capture: true,
    can_cancel: true,
    can_fund_escrow: false,
    ...over,
  };
}

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  Object.values(api).forEach((m) => m.mockReset());
  api.getPaypalConfig.mockResolvedValue({ simulated: true, enabled: true, client_id: "cid", charge_currency: "USD" });
  api.listDealPayments.mockResolvedValue({ simulated: true, payments: [] });
  window.paypal = {
    Buttons: (c) => {
      cfg = c;
      return { render: () => Promise.resolve() };
    },
  };
});

function mount(d = deal()) {
  const onChanged = vi.fn();
  render(
    <I18nProvider>
      <ToastProvider>
        <PaypalCheckout deal={d} onChanged={onChanged} />
      </ToastProvider>
    </I18nProvider>,
  );
  return { onChanged };
}

describe("PaypalCheckout", () => {
  it("shows a muted note and no buttons when not configured", async () => {
    api.getPaypalConfig.mockResolvedValue({ simulated: true, enabled: false, client_id: null, charge_currency: "USD" });
    mount();
    expect(await screen.findByTestId("pp-disabled")).toHaveTextContent("PayPal Sandbox is not configured");
    expect(screen.queryByTestId("pp-buttons")).toBeNull();
  });

  it("renders nothing for a supplier", () => {
    mount(deal({ viewer_role: "SUPPLIER" }));
    expect(screen.queryByText("Pay with PayPal Sandbox")).toBeNull();
  });

  it("renders the Simulated card with PayPal buttons", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "Pay with PayPal Sandbox" })).toBeInTheDocument();
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
    await waitFor(() => expect(cfg).toBeDefined());
  });

  it("creates, captures and cancels through the API without sending an amount", async () => {
    api.createPaypalOrder.mockResolvedValue(payment());
    api.capturePaypalOrder.mockResolvedValue(payment({ status: "CAPTURED" }));
    api.cancelPaypalOrder.mockResolvedValue(payment({ status: "CANCELLED" }));
    mount();
    await waitFor(() => expect(cfg).toBeDefined());
    let id = "";
    await act(async () => {
      id = await cfg.createOrder();
    });
    expect(id).toBe("ORDER-1");
    const [dealId, key, ...rest] = api.createPaypalOrder.mock.calls[0];
    expect(dealId).toBe(deal().id);
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(rest).toEqual([]);
    await act(async () => {
      await cfg.onApprove({ orderID: id });
    });
    expect(api.capturePaypalOrder).toHaveBeenCalledWith("pay-1");
    expect(await screen.findByTestId("pp-status")).toHaveTextContent("Payment captured");
    await act(async () => {
      await cfg.createOrder();
      cfg.onCancel();
    });
    expect(api.cancelPaypalOrder).toHaveBeenCalledWith("pay-1");
    expect(screen.getByTestId("pp-status")).toHaveTextContent("Payment cancelled");
  });

  it("shows an error and lets the user retry", async () => {
    api.createPaypalOrder.mockRejectedValue(new ApiError(500, "x"));
    mount();
    await waitFor(() => expect(cfg).toBeDefined());
    await act(async () => {
      cfg.onError(new ApiError(500, "x"));
    });
    expect(screen.getByTestId("pp-status")).toHaveTextContent("could not be completed");
    expect(screen.getByTestId("pp-buttons")).toBeInTheDocument();
  });

  it("offers escrow deposit only for a captured payment that can fund", async () => {
    api.listDealPayments.mockResolvedValue({
      simulated: true,
      payments: [
        payment({ id: "a", status: "CREATED" }),
        payment({ id: "b", status: "CAPTURED", can_fund_escrow: false }),
      ],
    });
    mount();
    await screen.findAllByTestId("pp-payment");
    expect(screen.queryByRole("button", { name: "Deposit into simulated escrow" })).toBeNull();
  });

  it("shows the pending-approval message on PENDING_APPROVAL", async () => {
    api.listDealPayments.mockResolvedValue({
      simulated: true,
      payments: [payment({ status: "CAPTURED", can_fund_escrow: true })],
    });
    api.fundEscrowFromPayment.mockResolvedValue({
      simulated: true,
      outcome: "PENDING_APPROVAL",
      idempotent_replay: false,
      approval_id: "ap1",
      approval_tier: 2,
      notice: "n",
      payment: payment({ status: "CAPTURED" }),
    });
    const { onChanged } = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Deposit into simulated escrow" }));
    fireEvent.click(await screen.findByRole("button", { name: "Deposit into escrow" }));
    const note = await screen.findByTestId("pp-pending");
    expect(note).toHaveTextContent("Waiting for approval - no money moved");
    expect(screen.getByRole("link", { name: "Open approvals" })).toHaveAttribute("href", "/app/approvals");
    expect(api.fundEscrowFromPayment).toHaveBeenCalledWith("pay-1");
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows the server message for a 409 refusal", async () => {
    api.listDealPayments.mockResolvedValue({
      simulated: true,
      payments: [payment({ status: "CAPTURED", can_fund_escrow: true })],
    });
    api.fundEscrowFromPayment.mockRejectedValue(new ApiError(409, "x", "Risk engine blocked this deposit", "RISK_BLOCKED"));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Deposit into simulated escrow" }));
    fireEvent.click(await screen.findByRole("button", { name: "Deposit into escrow" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Risk engine blocked this deposit");
  });
});
