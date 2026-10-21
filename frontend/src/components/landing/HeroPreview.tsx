"use client";

import { useEffect, useState } from "react";

import { useT } from "@/i18n";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/Icon";
import { KpiCard } from "@/components/ui/KpiCard";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { Stepper } from "@/components/ui/Stepper";
import { TierBadge } from "@/components/ui/TierBadge";

import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

const STATES = [0, 1, 2] as const;
export const HERO_CYCLE_MS = 5000;

function CashflowState() {
  const t = useT();
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          label={t("landing.preview.kpiCash")}
          value="৳ 4,80,000"
          spark={{ points: [9, 8, 8, 7, 6, 5, 3], label: t("landing.preview.sparkLabel") }}
        />
        <KpiCard
          label={t("landing.preview.kpiDue")}
          value="৳ 6,36,000"
          delta={{ text: t("landing.preview.kpiDueDelta"), tone: "warning" }}
        />
      </div>
      <Alert tone="warning" title={t("landing.preview.shortTitle")}>
        {t("landing.preview.shortBody")}
      </Alert>
    </div>
  );
}

function ApprovalState() {
  const t = useT();
  const steps = (["verify", "escrow", "check", "release"] as const).map((id) => ({
    id,
    label: t(`landing.how.${id}.name`),
  }));
  return (
    <div className="grid gap-3 rounded-card border border-line bg-surface p-4">
      <Stepper steps={steps} current={3} label={t("landing.how.label")} />
      <div className="flex flex-wrap items-center gap-2">
        <TierBadge tier={3} />
        <Badge tone="info" icon={<Icon name="clock" size={12} />}>
          {t("landing.preview.cooling")}
        </Badge>
      </div>
      <p className="text-sm font-semibold text-ink">{t("landing.preview.approveTitle")}</p>
      <p className="text-sm text-muted">{t("landing.preview.approveBody")}</p>
      <div className="flex gap-2">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            className="flex size-9 items-center justify-center rounded-lg border border-line bg-surface-alt text-lg font-bold text-ink"
          >
            {i < 4 ? "•" : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

function BlockedState() {
  const t = useT();
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <TierBadge tier={3} decision="BLOCK" />
        <Badge tone="danger" icon={<Icon name="eye" size={12} />}>
          {t("landing.preview.hidden")}
        </Badge>
      </div>
      <Alert tone="danger" title={t("landing.preview.blockTitle")}>
        {t("landing.preview.blockBody")}
      </Alert>
      <p className="rounded-lg border border-line bg-surface-alt p-3 text-xs text-muted">
        {t("landing.preview.blockDoc")}
      </p>
    </div>
  );
}

/** Decorative, hard-coded fictional demo data; the text alternative is the caption below the mock. */
export function HeroPreview() {
  const t = useT();
  const reduced = usePrefersReducedMotion();
  const [index, setIndex] = useState(0);
  const [userPaused, setUserPaused] = useState(false);
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const running = !reduced && !userPaused && !hover && !focus;

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setIndex((i) => (i + 1) % STATES.length), HERO_CYCLE_MS);
    return () => clearInterval(id);
  }, [running]);

  return (
    <section
      aria-label={t("landing.preview.label")}
      className="min-w-0"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
    >
      <div className="rounded-hero bg-surface p-4 shadow-pop sm:p-5">
        <div className="mb-3 flex items-center justify-between gap-2">
          <SimulatedBadge />
          <span className="text-xs font-semibold text-muted">{t("landing.preview.fictional")}</span>
        </div>
        <div aria-hidden="true" className="min-h-72">
          <div key={index} className="anim-fade-up">
            {index === 0 ? <CashflowState /> : index === 1 ? <ApprovalState /> : <BlockedState />}
          </div>
        </div>
        <p className="mt-3 text-sm text-muted" data-testid="hero-caption">
          {t(`landing.preview.caption.${index}`)}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div role="group" aria-label={t("landing.preview.tabs")} className="flex flex-wrap gap-2">
            {STATES.map((s) => (
              <button
                key={s}
                type="button"
                aria-pressed={index === s}
                onClick={() => setIndex(s)}
                className={`min-h-11 rounded-xl border px-3 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
                  index === s
                    ? "border-brand-700 bg-brand-700 text-white"
                    : "border-line text-ink hover:bg-surface-alt"
                }`}
              >
                {t(`landing.preview.tab.${s}`)}
              </button>
            ))}
          </div>
          {!reduced ? (
            <button
              type="button"
              aria-pressed={userPaused}
              onClick={() => setUserPaused((p) => !p)}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-brand-text hover:bg-brand-50 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <Icon name={userPaused ? "play" : "clock"} size={16} />
              {userPaused ? t("landing.preview.play") : t("landing.preview.pause")}
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
