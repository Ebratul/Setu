"use client";

import { Card } from "@/components/ui/Card";
import { useLang, useT } from "@/i18n";
import type { ActivityOut } from "@/lib/api/deals";

const TIER: Record<number, { icon: string; cls: string }> = {
  0: { icon: "○", cls: "border-line bg-surface-alt text-ink" },
  1: { icon: "i", cls: "border-info bg-info-soft text-info" },
  2: { icon: "▲", cls: "border-warning bg-warning-soft text-warning" },
  3: { icon: "✕", cls: "border-danger bg-danger-soft text-danger" },
};

export function ActivityList({ activity }: { activity: ActivityOut }) {
  const t = useT();
  const { lang } = useLang();
  return (
    <Card as="section" labelledBy="act-h" className="space-y-3">
      <h2 id="act-h" className="text-lg font-bold text-ink">
        {t("act.title")}
      </h2>
      {activity.rows.length === 0 ? (
        <p className="text-sm text-muted">{t("act.empty")}</p>
      ) : (
        <ul className="divide-y divide-line">
          {activity.rows.map((r) => {
            const tier = TIER[r.tier] ?? TIER[0];
            return (
              <li key={r.seq} data-testid="activity-row" className="space-y-1 py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-ink">{r.action}</span>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${tier.cls}`}
                  >
                    <span aria-hidden="true">{tier.icon}</span>
                    {t("act.tier", { tier: r.tier })}
                  </span>
                  <span className="text-xs text-muted">
                    {t(`act.actor.${r.actor}`)} · {r.result}
                  </span>
                </div>
                <p className="text-xs text-muted">
                  #{r.seq} ·{" "}
                  {new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-US", {
                    dateStyle: "medium",
                    timeStyle: "short",
                    timeZone: "Asia/Dhaka",
                  }).format(new Date(r.ts))}
                  {" · "}
                  <span title={r.entry_hash}>{t("act.hash")} {r.entry_hash.slice(0, 10)}…</span>
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
