"use client";

import { useT } from "@/i18n";

type Props = { step: "SUBMITTED" | "APPROVED"; working: boolean };

const STEPS = ["SUBMITTED", "APPROVED"] as const;

export function ApplicationTracker({ step, working }: Props) {
  const t = useT();
  const at = STEPS.indexOf(step);
  return (
    <ol
      aria-label={t("fin.apply.tracker")}
      className="flex flex-wrap items-center gap-3 text-sm"
    >
      {STEPS.map((s, i) => {
        const done = i < at || (i === at && s === "APPROVED");
        const current = i === at && !done;
        return (
          <li
            key={s}
            aria-current={current ? "step" : undefined}
            className={`flex items-center gap-2 rounded-full border px-3 py-1 font-semibold ${
              done
                ? "border-success bg-success-soft text-success"
                : current
                  ? "border-info bg-info-soft text-info"
                  : "border-line bg-surface-alt text-muted"
            }`}
          >
            <span
              aria-hidden="true"
              className={current && working ? "motion-safe:animate-pulse" : ""}
            >
              {done ? "✓" : current ? "●" : "○"}
            </span>
            {t(`fin.status.${s}`)}
          </li>
        );
      })}
    </ol>
  );
}
