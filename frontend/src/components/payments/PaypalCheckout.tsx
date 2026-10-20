"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { dealErrorText } from "@/lib/api/dealErrors";
import type { DealDetail } from "@/lib/api/deals";
import {
  cancelPaypalOrder,
  capturePaypalOrder,
  createPaypalOrder,
  fundEscrowFromPayment,
  getPaypalConfig,
  listDealPayments,
  newPaymentKey,
  type PaymentOut,
} from "@/lib/api/payments";
import { formatDate, formatMoney } from "@/lib/format";
import { useApi } from "@/lib/useApi";

import { loadPaypalSdk } from "./paypalSdk";

type Props = { deal: DealDetail; onChanged: () => void };
type Sdk = "idle" | "loading" | "ready" | "error";

const TONE: Record<PaymentOut["status"], Tone> = {
  CREATED: "info",
  CAPTURED: "success",
  FAILED: "danger",
  CANCELLED: "neutral",
};

export function PaypalCheckout({ deal, onChanged }: Props) {
  const t = useT();
  const role = deal.viewer_role;
  const allowed = (role === "BUYER" || role === "ADMIN") && deal.can.can_fund.allowed;
  if (!allowed) return null;
  return <CheckoutCard deal={deal} onChanged={onChanged} t={t} />;
}

function CheckoutCard({
  deal,
  onChanged,
  t,
}: Props & { t: (k: string, v?: Record<string, string | number>) => string }) {
  const { lang } = useLang();
  const toast = useToast();
  const config = useApi((s) => getPaypalConfig(s), "paypal-config");
  const [tick, setTick] = useState(0);
  const payments = useApi((s) => listDealPayments(deal.id, s), `paypal-pay|${deal.id}|${tick}`);
  const [sdk, setSdk] = useState<Sdk>("idle");
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [fundTarget, setFundTarget] = useState<PaymentOut | null>(null);
  const [fundBusy, setFundBusy] = useState(false);
  const [fundError, setFundError] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const keyRef = useRef<string | null>(null);
  const activeRef = useRef<PaymentOut | null>(null);

  const cfg = config.data;
  const clientId = cfg?.enabled ? cfg.client_id : null;

  const errText = (e: unknown) => {
    if (e instanceof ApiError && e.code && e.detail && e.status === 409) return e.detail;
    return dealErrorText(e, t);
  };
  const refresh = () => setTick((n) => n + 1);

  const handlers = useRef({
    create: async (): Promise<string> => "",
    approve: async (): Promise<void> => {},
    cancel: (): void => {},
    error: (_e: unknown): void => {},
  });
  useEffect(() => {
    handlers.current = {
      create: async () => {
        setMessage(null);
        keyRef.current ??= newPaymentKey();
        const p = await createPaypalOrder(deal.id, keyRef.current);
        activeRef.current = p;
        return p.provider_order_id;
      },
      approve: async () => {
        const p = activeRef.current;
        if (!p) return;
        const done = await capturePaypalOrder(p.id);
        activeRef.current = null;
        keyRef.current = null;
        setMessage({
          text:
            done.status === "CAPTURED"
              ? t("pp.captured", {
                  charge: formatMoney(done.charge_amount, done.charge_currency, lang),
                })
              : t("pp.notCaptured"),
          error: done.status !== "CAPTURED",
        });
        refresh();
      },
      cancel: () => {
        const p = activeRef.current;
        activeRef.current = null;
        keyRef.current = null;
        setMessage({ text: t("pp.cancelled"), error: false });
        if (p) cancelPaypalOrder(p.id).then(refresh, () => undefined);
      },
      error: (e) => {
        setMessage({ text: `${t("pp.error")} ${errText(e)}`, error: true });
        refresh();
      },
    };
  });

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    let closer: (() => Promise<void> | void) | undefined;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSdk("loading");
    loadPaypalSdk(clientId).then(
      (paypal) => {
        if (cancelled || !host.current) return;
        const b = paypal.Buttons({
          style: { layout: "vertical", label: "paypal" },
          createOrder: () => handlers.current.create(),
          onApprove: () => handlers.current.approve(),
          onCancel: () => handlers.current.cancel(),
          onError: (e) => handlers.current.error(e),
        });
        closer = b.close?.bind(b);
        host.current.replaceChildren();
        b.render(host.current).then(
          () => !cancelled && setSdk("ready"),
          () => !cancelled && setSdk("error"),
        );
      },
      () => !cancelled && setSdk("error"),
    );
    return () => {
      cancelled = true;
      void closer?.();
    };
  }, [clientId]);

  async function fund() {
    if (!fundTarget) return;
    setFundBusy(true);
    setFundError(null);
    try {
      const res = await fundEscrowFromPayment(fundTarget.id);
      setFundTarget(null);
      if (res.outcome === "PENDING_APPROVAL") {
        setPendingApproval(true);
        toast(t("pp.fundPending"), "info");
      } else {
        toast(t("pp.funded"), "success");
      }
      refresh();
      onChanged();
    } catch (e) {
      setFundError(errText(e));
    } finally {
      setFundBusy(false);
    }
  }

  const list = payments.data?.payments ?? [];

  return (
    <Card as="section" labelledBy="pp-h" className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="pp-h" className="text-lg font-bold text-ink">
          {t("pp.title")}
        </h2>
        <SimulatedBadge />
      </div>
      <p className="text-sm text-muted">{t("pp.lead")}</p>
      <p className="rounded-xl border border-warning bg-warning-soft p-3 text-sm font-medium text-ink">
        {t("pp.notEscrow")}
      </p>

      {config.error ? (
        <p role="alert" className="text-sm font-medium text-danger">
          {t("pp.configError")}
        </p>
      ) : cfg && !cfg.enabled ? (
        <p data-testid="pp-disabled" className="text-sm text-muted">
          {t("pp.notConfigured")}
        </p>
      ) : cfg ? (
        <div className="space-y-2">
          <h3 className="text-sm font-bold text-ink">{t("pp.step1")}</h3>
          {sdk === "loading" ? <p className="text-sm text-muted">{t("pp.loading")}</p> : null}
          {sdk === "error" ? (
            <p role="alert" className="text-sm font-medium text-danger">
              {t("pp.sdkError")}
            </p>
          ) : null}
          <div ref={host} data-testid="pp-buttons" aria-label={t("pp.buttonsLabel")} />
        </div>
      ) : (
        <p className="text-sm text-muted">{t("pp.loading")}</p>
      )}

      <div aria-live="polite" role="status" data-testid="pp-status">
        {message ? (
          <p className={`text-sm font-semibold ${message.error ? "text-danger" : "text-success"}`}>
            {message.error ? "✕ " : "✓ "}
            {message.text}
          </p>
        ) : null}
        {pendingApproval ? (
          <p className="text-sm font-semibold text-ink" data-testid="pp-pending">
            {t("pp.fundPending")}{" "}
            <Link
              href="/app/approvals"
              className="text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              {t("pp.openApprovals")}
            </Link>
          </p>
        ) : null}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-bold text-ink">{t("pp.step2")}</h3>
        {payments.error ? (
          <p role="alert" className="text-sm text-danger">
            {dealErrorText(payments.error, t)}
          </p>
        ) : list.length === 0 ? (
          <p className="text-sm text-muted">{t("pp.none")}</p>
        ) : (
          <ul className="space-y-3">
            {list.map((p) => (
              <li
                key={p.id}
                data-testid="pp-payment"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3 text-sm"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={TONE[p.status]}>{t(`pp.status.${p.status}`)}</Badge>
                    <span className="text-muted">{formatDate(p.created_at.slice(0, 10), lang)}</span>
                  </div>
                  <p className="text-ink">
                    {t("pp.amounts", {
                      charge: formatMoney(p.charge_amount, p.charge_currency, lang),
                      deposit: formatMoney(p.amount, p.currency, lang),
                    })}
                  </p>
                  {p.escrow_funded_at ? (
                    <p className="font-semibold text-success">✓ {t("pp.alreadyFunded")}</p>
                  ) : null}
                </div>
                {p.status === "CAPTURED" && p.can_fund_escrow ? (
                  <Button
                    onClick={() => {
                      setFundError(null);
                      setFundTarget(p);
                    }}
                  >
                    {t("pp.fundButton")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      {fundTarget ? (
        <ConfirmDialog
          title={t("pp.fundTitle")}
          confirmLabel={t("pp.fundConfirm")}
          busy={fundBusy}
          error={fundError}
          onClose={() => setFundTarget(null)}
          onConfirm={fund}
        >
          <p>
            {t("pp.fundBody", {
              deposit: formatMoney(fundTarget.amount, fundTarget.currency, lang),
            })}
          </p>
          <p className="text-xs text-muted">{t("pp.simNote")}</p>
        </ConfirmDialog>
      ) : null}
    </Card>
  );
}
