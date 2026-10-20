import type { components } from "./schema.gen";
import { apiGet, apiPost } from "./client";

type S = components["schemas"];
export type PaymentOut = S["PaymentOut"];
export type PaypalConfig = S["PaypalConfigOut"];
export type FundEscrowResult = S["FundEscrowResult"];
export type PaymentCoverage = PaymentOut["coverage"];

const enc = encodeURIComponent;
const opts = (signal?: AbortSignal) => ({ signal, cache: "no-store" as const });

/** 8-64 chars of [A-Za-z0-9_-]; one per checkout click session. */
export function newPaymentKey(): string {
  const rnd =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now()}${Math.random().toString(36).slice(2)}`;
  return `pp${rnd}`.slice(0, 64);
}

export const getPaypalConfig = (signal?: AbortSignal) =>
  apiGet<PaypalConfig>("/payments/paypal/config", opts(signal));

/** The body carries only the deal and coverage; the server decides every amount. */
export const createPaypalOrder = (
  dealId: string,
  idempotencyKey: string,
  coverage?: PaymentCoverage,
) =>
  apiPost<PaymentOut>(
    "/payments/paypal/orders",
    coverage ? { deal_id: dealId, coverage } : { deal_id: dealId },
    { headers: { "Idempotency-Key": idempotencyKey } },
  );

export const capturePaypalOrder = (paymentId: string) =>
  apiPost<PaymentOut>(`/payments/paypal/orders/${enc(paymentId)}/capture`);

export const cancelPaypalOrder = (paymentId: string) =>
  apiPost<PaymentOut>(`/payments/paypal/orders/${enc(paymentId)}/cancel`);

export const getPaypalPayment = (paymentId: string, refresh = false) =>
  apiGet<PaymentOut>(`/payments/paypal/${enc(paymentId)}${refresh ? "?refresh=true" : ""}`, {
    cache: "no-store",
  });

export const listDealPayments = (dealId: string, signal?: AbortSignal) =>
  apiGet<S["PaymentListOut"]>(`/payments/paypal/deals/${enc(dealId)}`, opts(signal));

export const fundEscrowFromPayment = (paymentId: string) =>
  apiPost<FundEscrowResult>(`/payments/paypal/${enc(paymentId)}/fund-escrow`);
