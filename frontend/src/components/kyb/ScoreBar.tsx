"use client";

import { useLang, useT } from "@/i18n";

const TONE = (s: number) =>
  s >= 80 ? "bg-success" : s >= 50 ? "bg-warning" : "bg-danger";

/** Display-only bar of a server-computed 0-100 score. */
export function ScoreBar({ score }: { score: number | null }) {
  const t = useT();
  const { lang } = useLang();
  if (score === null) return <span className="text-muted">—</span>;
  const n = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-US").format(score);
  return (
    <div
      className="flex min-w-24 items-center gap-2"
      role="img"
      aria-label={t("kyb.scoreLabel", { score: n })}
    >
      <div className="h-2 w-16 overflow-hidden rounded-full bg-line sm:w-20">
        <div
          className={`h-full ${TONE(score)}`}
          style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
        />
      </div>
      <span className="text-sm font-bold text-ink tabular-nums" aria-hidden="true">
        {n}
      </span>
    </div>
  );
}
