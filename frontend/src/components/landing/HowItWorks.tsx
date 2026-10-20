"use client";

import { useId, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Icon, type IconName } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { TierBadge } from "@/components/ui/TierBadge";
import { useT } from "@/i18n";

import { Section } from "./Section";

const STEPS = ["verify", "escrow", "check", "release"] as const;
type StepId = (typeof STEPS)[number];
const ICONS: Record<StepId, IconName> = { verify: "users", escrow: "lock", check: "file", release: "coins" };

function Thumb({ step }: { step: StepId }) {
  const t = useT();
  const supplier = t("landing.fictional.supplier");
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-ink">{supplier}</p>
        <SimulatedBadge />
      </div>
      {step === "verify" ? (
        <>
          <Badge tone="success">{t("landing.how.verify.thumb1")}</Badge>
          <Badge tone="success">{t("landing.how.verify.thumb2")}</Badge>
        </>
      ) : null}
      {step === "escrow" ? (
        <>
          <p className="text-2xl font-bold text-ink">¥ 360,000</p>
          <Badge tone="info" icon={<Icon name="lock" size={12} />}>
            {t("landing.how.escrow.thumb1")}
          </Badge>
          <p className="text-sm text-muted">{t("landing.how.escrow.thumb2")}</p>
        </>
      ) : null}
      {step === "check" ? (
        <>
          <Alert tone="danger" title={t("landing.how.check.thumb1")}>
            {t("landing.how.check.thumb2")}
          </Alert>
        </>
      ) : null}
      {step === "release" ? (
        <>
          <TierBadge tier={2} />
          <p className="text-sm text-ink">{t("landing.how.release.thumb1")}</p>
          <Badge tone="success">{t("landing.how.release.thumb2")}</Badge>
        </>
      ) : null}
    </div>
  );
}

export function HowItWorks() {
  const t = useT();
  const base = useId();
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKey = (e: React.KeyboardEvent, i: number) => {
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % STEPS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i + STEPS.length - 1) % STEPS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = STEPS.length - 1;
    else return;
    e.preventDefault();
    setActive(next);
    refs.current[next]?.focus();
  };

  return (
    <Section id="how" title={t("landing.how.title")} lead={t("landing.how.lead")} alt>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div role="tablist" aria-label={t("landing.how.label")} aria-orientation="vertical" className="grid gap-3">
          {STEPS.map((s, i) => (
            <button
              key={s}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${s}`}
              aria-selected={active === i}
              aria-controls={`${base}-panel`}
              tabIndex={active === i ? 0 : -1}
              onClick={() => setActive(i)}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onKeyDown={(e) => onKey(e, i)}
              className={`flex min-h-11 items-start gap-4 rounded-card border p-4 text-start transition-colors focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                active === i ? "border-brand-700 bg-surface shadow-card-hover" : "border-line bg-surface hover:bg-brand-50"
              }`}
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-700 font-bold text-white">
                {i + 1}
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-lg font-bold text-ink">
                  <Icon name={ICONS[s]} size={18} />
                  {t(`landing.how.${s}.name`)}
                </span>
                <span className="mt-1 block text-sm text-muted">{t(`landing.how.${s}.desc`)}</span>
              </span>
            </button>
          ))}
        </div>
        <div
          role="tabpanel"
          id={`${base}-panel`}
          aria-labelledby={`${base}-tab-${STEPS[active]}`}
          tabIndex={0}
          className="rounded-hero bg-surface p-5 shadow-card focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          <Thumb step={STEPS[active]} />
        </div>
      </div>
    </Section>
  );
}
