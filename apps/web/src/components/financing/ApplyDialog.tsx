"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Money } from "@/components/analysis/Money";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import { ApiError } from "@/lib/api/client";
import {
  applyFinancing,
  simulateApproval,
  type FinMode,
  type OptionQuote,
} from "@/lib/api/financing";
import { formatDate } from "@/lib/format";

import { ApplicationTracker } from "./ApplicationTracker";

type Phase = "confirm" | "submitting" | "submitted" | "approved" | "error";

type Props = {
  option: OptionQuote;
  amount: string;
  mode: FinMode;
  dealId: string;
  partyId: string | undefined;
  currency: Currency;
  approveDelayMs?: number;
  onClose: (changed: boolean) => void;
};

export function ApplyDialog({
  option,
  amount,
  mode,
  dealId,
  partyId,
  currency,
  approveDelayMs = 1500,
  onClose,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const [phase, setPhase] = useState<Phase>("confirm");
  const [problem, setProblem] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  function fail(e: unknown) {
    setPhase("error");
    if (e instanceof ApiError && e.status === 403)
      setProblem(t("fin.readOnly"));
    else if (e instanceof ApiError && e.detail) setProblem(e.detail);
    else setProblem(t("error.body"));
  }

  function approve(id: string) {
    timer.current = setTimeout(() => {
      simulateApproval(id).then(
        () => setPhase("approved"),
        (e: unknown) => {
          fail(e);
        },
      );
    }, approveDelayMs);
  }

  function submit() {
    setPhase("submitting");
    setProblem(null);
    applyFinancing({
      deal_id: dealId,
      party_id: partyId,
      option_id: option.code,
      amount,
      mode,
    }).then((app) => {
      if (app.status === "APPROVED") {
        setPhase("approved");
      } else {
        setPhase("submitted");
        approve(app.id);
      }
    }, fail);
  }

  const busy = phase === "submitting" || phase === "submitted";
  const rows: [string, React.ReactNode][] = [
    [t("fin.opt.name"), option.name],
    [
      t("fin.apply.amount"),
      <Money key="a" amounts={option.principal} currency={currency} />,
    ],
    [
      t("fin.opt.total"),
      <Money key="t" amounts={option.cost.total} currency={currency} />,
    ],
    [t("fin.opt.tenor"), t("fin.days", { n: option.tenor_days })],
    [t("fin.opt.maturity"), formatDate(option.maturity_on, lang)],
  ];
  return (
    <Modal
      title={t("fin.apply.title")}
      closeDisabled={busy}
      onClose={() => onClose(phase === "approved")}
    >
      <div className="space-y-4">
        <SimulatedBadge />
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="rounded-xl border border-warning bg-warning-soft p-3 text-sm font-semibold text-warning">
          {t("fin.apply.simulatedNote")}
        </p>

        {phase !== "confirm" && phase !== "error" ? (
          <ApplicationTracker
            step={phase === "approved" ? "APPROVED" : "SUBMITTED"}
            working={busy}
          />
        ) : null}

        <div aria-live="polite" className="space-y-3">
          {phase === "submitting" ? (
            <p className="text-sm text-muted">{t("fin.apply.submitting")}</p>
          ) : null}
          {phase === "submitted" ? (
            <p className="text-sm text-muted">{t("fin.apply.waiting")}</p>
          ) : null}
          {phase === "approved" ? (
            <div className="rounded-xl border border-success bg-success-soft p-3 text-sm font-semibold text-success">
              <p>{t("fin.apply.approved")}</p>
              <Link
                href="/app"
                className="mt-1 inline-block underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
              >
                {t("fin.apply.toDashboard")}
              </Link>
            </div>
          ) : null}
        </div>
        {phase === "error" && problem ? (
          <p
            role="alert"
            className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-semibold text-danger"
          >
            {problem}
          </p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          {phase === "confirm" || phase === "error" ? (
            <>
              <Button variant="secondary" onClick={() => onClose(false)}>
                {t("common.cancel")}
              </Button>
              <Button onClick={submit}>{t("fin.apply.confirm")}</Button>
            </>
          ) : null}
          {phase === "approved" ? (
            <Button onClick={() => onClose(true)}>{t("common.close")}</Button>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
