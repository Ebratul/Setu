"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useT } from "@/i18n";
import type { AppUser } from "@/lib/api/auth";
import { useShellUser } from "@/lib/MeContext";
import { dismissWelcome, shouldShowWelcome } from "@/lib/welcome";

const STEPS = ["welcome", "order", "escrow"] as const;

/** First ACTIVE visit after onboarding: welcome, a three-step first-order tour. */
export function WelcomeTour({ user }: { user?: AppUser }) {
  const t = useT();
  const ctx = useShellUser();
  const me = user ?? ctx;
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const active = me?.account_status === "ACTIVE";
  const userId = me?.id;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (active && userId && shouldShowWelcome(userId)) setOpen(true);
  }, [active, userId]);

  if (!open || !me || !userId) return null;
  const supplier = me.role === "SUPPLIER";
  const close = () => {
    dismissWelcome(userId);
    setOpen(false);
  };

  const key = STEPS[step];
  const last = step === STEPS.length - 1;
  const firstOrder = supplier ? "/supplier" : "/app/deals/new";

  return (
    <Modal
      title={t(`wt.${key}.title`, { name: me.display_name })}
      onClose={close}
    >
      <div className="space-y-4 text-sm text-ink">
        <p className="text-xs font-semibold text-muted" aria-live="polite">
          {t("wt.progress", { n: step + 1, total: STEPS.length })}
        </p>
        <p>{t(`wt.${key}.body${supplier ? ".supplier" : ""}`)}</p>
        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="ghost" onClick={close}>
            {t("wt.skip")}
          </Button>
          <div className="flex flex-wrap gap-2">
            {step > 0 ? (
              <Button variant="secondary" onClick={() => setStep(step - 1)}>
                {t("ob.back")}
              </Button>
            ) : null}
            {last ? (
              <Link
                href={firstOrder}
                onClick={close}
                className="inline-flex min-h-11 items-center justify-center rounded-xl bg-brand-700 px-4 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
              >
                {supplier ? t("wt.finish.supplier") : t("wt.finish")}
              </Link>
            ) : (
              <Button onClick={() => setStep(step + 1)}>{t("ob.next")}</Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
