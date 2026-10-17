"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FormField, inputClass } from "@/components/ui/FormField";
import { useToast } from "@/components/ui/Toast";
import { useLang, useT } from "@/i18n";
import { dealErrorText } from "@/lib/api/dealErrors";
import {
  confirmMilestones,
  fundEscrow,
  newIdempotencyKey,
  proposeMilestones,
  releaseMilestone,
  type ActionFlag,
  type DealDetail,
  type Milestone,
} from "@/lib/api/deals";
import { isDecimal, isZero, sumDecimals } from "@/lib/decimal";
import { formatMoney } from "@/lib/format";

type Props = { deal: DealDetail; onChanged: () => void };
type Dialog = "propose" | "confirm" | "fund" | null;

function ActionButton({
  flag,
  id,
  onClick,
  children,
}: {
  flag: ActionFlag;
  id: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <Button
        disabled={!flag.allowed}
        aria-describedby={flag.allowed ? undefined : `${id}-why`}
        onClick={onClick}
        data-testid={`action-${id}`}
      >
        {children}
      </Button>
      {!flag.allowed && flag.reason ? (
        <p id={`${id}-why`} className="mt-1 max-w-xs text-xs text-muted">
          {flag.reason}
        </p>
      ) : null}
    </div>
  );
}

/** Propose / Confirm / Fund buttons driven by the server's can_* flags. Release lives in ReleaseDialog. */
export function DealActions({ deal, onChanged }: Props) {
  const t = useT();
  const [open, setOpen] = useState<Dialog>(null);
  const role = deal.viewer_role;
  const buyerSide = role === "BUYER" || role === "ADMIN";
  const close = () => setOpen(null);
  if (role === "JUDGE") return null;

  return (
    <section aria-labelledby="actions-h" className="space-y-3">
      <h2 id="actions-h" className="text-lg font-bold text-ink">
        {t("act2.title")}
      </h2>
      <div className="flex flex-wrap items-start gap-4">
        {buyerSide ? (
          <ActionButton id="propose" flag={deal.can.can_propose} onClick={() => setOpen("propose")}>
            {t("act2.propose")}
          </ActionButton>
        ) : null}
        {role !== "ADMIN" ? (
          <ActionButton id="confirm" flag={deal.can.can_confirm} onClick={() => setOpen("confirm")}>
            {t("act2.confirm")}
          </ActionButton>
        ) : null}
        {buyerSide ? (
          <ActionButton id="fund" flag={deal.can.can_fund} onClick={() => setOpen("fund")}>
            {t("act2.fund")}
          </ActionButton>
        ) : null}
      </div>
      {open === "propose" ? (
        <ProposeDialog deal={deal} onClose={close} onDone={onChanged} />
      ) : null}
      {open === "confirm" ? (
        <ConfirmScheduleDialog deal={deal} onClose={close} onDone={onChanged} />
      ) : null}
      {open === "fund" ? (
        <FundDialog deal={deal} onClose={close} onDone={onChanged} />
      ) : null}
    </section>
  );
}

type DialogProps = { deal: DealDetail; onClose: () => void; onDone: () => void };

function useAction(onClose: () => void, onDone: () => void, successKey: string) {
  const t = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      toast(t(successKey), "success");
      onDone();
      onClose();
    } catch (e) {
      setError(dealErrorText(e, t));
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function ProposeDialog({ deal, onClose, onDone }: DialogProps) {
  const t = useT();
  const [mode, setMode] = useState<"30/60/10" | "custom">("30/60/10");
  const [percents, setPercents] = useState<string[]>(["30", "60", "10"]);
  const { busy, error, run } = useAction(onClose, onDone, "act2.proposed");

  const sum = mode === "custom" ? sumDecimals(percents) : "100";
  const valid =
    mode === "30/60/10" ||
    (percents.length >= 2 &&
      percents.length <= 5 &&
      percents.every((p) => isDecimal(p) && !isZero(p)) &&
      sum === "100");

  return (
    <ConfirmDialog
      title={t("act2.proposeTitle")}
      confirmLabel={t("act2.propose")}
      busy={busy}
      error={error}
      confirmDisabled={!valid}
      onClose={onClose}
      onConfirm={() =>
        run(() =>
          proposeMilestones(deal.id, {
            template: mode,
            percents: mode === "custom" ? percents.map((p) => p.trim()) : null,
          }),
        )
      }
    >
      <p>{t("act2.proposeBody")}</p>
      <fieldset className="space-y-2">
        <legend className="font-semibold">{t("act2.template")}</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="tpl"
            checked={mode === "30/60/10"}
            onChange={() => setMode("30/60/10")}
            className="focus-visible:ring-2 focus-visible:ring-brand-500"
          />
          {t("act2.tpl3060")}
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="tpl"
            checked={mode === "custom"}
            onChange={() => setMode("custom")}
            className="focus-visible:ring-2 focus-visible:ring-brand-500"
          />
          {t("act2.tplCustom")}
        </label>
      </fieldset>
      {mode === "custom" ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {percents.map((p, i) => (
              <FormField key={i} id={`pct-${i}`} label={t("act2.pctN", { n: i + 1 })}>
                {(aria) => (
                  <input
                    {...aria}
                    type="text"
                    inputMode="decimal"
                    value={p}
                    onChange={(e) =>
                      setPercents((xs) => xs.map((x, j) => (j === i ? e.target.value : x)))
                    }
                    className={inputClass}
                  />
                )}
              </FormField>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              disabled={percents.length >= 5}
              onClick={() => setPercents((xs) => [...xs, "0"])}
            >
              {t("act2.addTranche")}
            </Button>
            <Button
              variant="secondary"
              disabled={percents.length <= 2}
              onClick={() => setPercents((xs) => xs.slice(0, -1))}
            >
              {t("act2.removeTranche")}
            </Button>
            <p
              aria-live="polite"
              data-testid="pct-sum"
              className={sum === "100" ? "font-semibold text-success" : "font-semibold text-danger"}
            >
              {sum === "100" ? "✓ " : "✕ "}
              {t("act2.pctSum", { sum: sum ?? "—" })}
            </p>
          </div>
        </div>
      ) : null}
    </ConfirmDialog>
  );
}

export function ConfirmScheduleDialog({ deal, onClose, onDone }: DialogProps) {
  const t = useT();
  const { busy, error, run } = useAction(onClose, onDone, "act2.confirmed");
  return (
    <ConfirmDialog
      title={t("act2.confirmTitle")}
      confirmLabel={t("act2.confirm")}
      busy={busy}
      error={error}
      onClose={onClose}
      onConfirm={() => run(() => confirmMilestones(deal.id))}
    >
      <p>{t("act2.confirmBody")}</p>
    </ConfirmDialog>
  );
}

function FundDialog({ deal, onClose, onDone }: DialogProps) {
  const t = useT();
  const { lang } = useLang();
  const [amount, setAmount] = useState("");
  const { busy, error, run } = useAction(onClose, onDone, "act2.funded");
  const c = deal.escrow.currency;
  const amountErr =
    amount.trim() === "" || (isDecimal(amount) && !isZero(amount))
      ? null
      : t("act2.amountInvalid");
  return (
    <ConfirmDialog
      title={t("act2.fundTitle")}
      confirmLabel={t("act2.fund")}
      busy={busy}
      error={error}
      confirmDisabled={amountErr !== null}
      onClose={onClose}
      onConfirm={() => run(() => fundEscrow(deal.id, amount.trim() || undefined))}
    >
      <p>{t("act2.fundBody", { remaining: formatMoney(deal.escrow.remaining_to_fund, c, lang) })}</p>
      <FormField id="fund-amount" label={t("act2.fundAmount", { currency: c })} hint={t("act2.fundHint")} error={amountErr}>
        {(aria) => (
          <input
            {...aria}
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className={inputClass}
          />
        )}
      </FormField>
      <p className="text-xs text-muted">{t("esc.simNote")}</p>
    </ConfirmDialog>
  );
}

type ReleaseProps = {
  deal: DealDetail;
  milestone: Milestone;
  onClose: () => void;
  onDone: () => void;
};

export function ReleaseDialog({ deal, milestone, onClose, onDone }: ReleaseProps) {
  const t = useT();
  const { lang } = useLang();
  const toast = useToast();
  const router = useRouter();
  const [key] = useState(() => newIdempotencyKey(milestone.id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const res = await releaseMilestone(milestone.id, key);
      onDone();
      if (res.outcome === "PENDING_APPROVAL") {
        setPending(true);
        setBusy(false);
        toast(t("ms.waitingApproval"), "info");
      } else {
        toast(t("ms.released"), "success");
        onClose();
      }
    } catch (e) {
      setError(dealErrorText(e, t));
      setBusy(false);
      onDone();
    }
  }

  if (pending) {
    return (
      <ConfirmDialog
        title={t("ms.waitingTitle")}
        confirmLabel={t("ms.openApprovals")}
        onClose={onClose}
        onConfirm={() => {
          router.push("/app/approvals");
        }}
      >
        <p data-testid="pending-approval-note">{t("ms.waitingApproval")}</p>
      </ConfirmDialog>
    );
  }
  return (
    <ConfirmDialog
      title={t("ms.releaseTitle", { seq: milestone.seq })}
      confirmLabel={t("ms.release")}
      busy={busy}
      error={error}
      onClose={onClose}
      onConfirm={go}
    >
      <p>
        {t("ms.releaseBody", {
          amount: formatMoney(milestone.amount, milestone.currency, lang),
          supplier: deal.supplier_name,
        })}
      </p>
      {deal.beneficiary_masked ? (
        <p className="text-muted">
          {t("ms.beneficiary", { account: deal.beneficiary_masked })}
        </p>
      ) : null}
      <p className="text-xs text-muted">{t("esc.simNote")}</p>
    </ConfirmDialog>
  );
}
