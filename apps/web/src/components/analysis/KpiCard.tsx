"use client";

import { Badge, toneClasses, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";

export type MarginBand = "healthy" | "thin" | "low";

const BAND_TONE: Record<MarginBand, Tone> = {
  healthy: "success",
  thin: "warning",
  low: "danger",
};
const BAND_ICON: Record<MarginBand, string> = {
  healthy: "▲",
  thin: "■",
  low: "▼",
};

type Props = {
  label: string;
  value: string;
  ariaLabel?: string;
  band?: MarginBand | null;
  hint?: string;
};

export function KpiCard({ label, value, ariaLabel, band, hint }: Props) {
  const t = useT();
  const tone: Tone = band ? BAND_TONE[band] : "neutral";
  return (
    <div
      data-tone={tone}
      data-testid="kpi-card"
      className={`rounded-card border-l-4 bg-surface p-5 shadow-card ${toneClasses[tone].split(" ")[0]}`}
    >
      <p className="text-sm font-medium text-muted">{label}</p>
      <p
        className="mt-1 text-2xl font-bold text-ink"
        aria-label={ariaLabel}
        title={ariaLabel}
      >
        {value}
      </p>
      {band ? (
        <div className="mt-2">
          <Badge tone={tone} icon={BAND_ICON[band]}>
            {t(`band.${band}`)}
          </Badge>
        </div>
      ) : null}
      {hint ? <p className="mt-2 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}
