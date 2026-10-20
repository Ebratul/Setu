"use client";

import { useT } from "@/i18n";

import { RING_CIRCUMFERENCE, RING_RADIUS, formatClock, ringState } from "./approvalLogic";

type Props = { left: number; total: number | null | undefined };

/** Cooling-off ring: the arc fills as the pause elapses. Reduced motion drops the transition (CSS), numbers stay. */
export function CoolingRing({ left, total }: Props) {
  const t = useT();
  const { dashoffset } = ringState(left, total);
  const done = left === 0;
  return (
    <div
      role="timer"
      aria-label={t("appr.t3.ring")}
      data-testid="cooling-ring"
      data-done={done}
      className="relative size-28 shrink-0"
    >
      <svg viewBox="0 0 100 100" className="size-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={RING_RADIUS} fill="none" strokeWidth="8" className="stroke-line" />
        <circle
          cx="50"
          cy="50"
          r={RING_RADIUS}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={dashoffset}
          className={`${done ? "stroke-success" : "stroke-brand-700"} transition-[stroke-dashoffset] duration-1000 ease-linear`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-xl font-bold text-ink tabular-nums" data-testid="cooling-time">
          {done ? "✓" : formatClock(left)}
        </span>
        <span className={done ? "text-xs text-muted" : "sr-only"}>
          {done ? t("appr.t3.ringDone") : t("appr.t3.ringLeft", { time: formatClock(left) })}
        </span>
      </div>
    </div>
  );
}
