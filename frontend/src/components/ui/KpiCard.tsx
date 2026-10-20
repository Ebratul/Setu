import type { ReactNode } from "react";

import { Badge, type Tone } from "./Badge";
import { Card } from "./Card";
import { Sparkline } from "./Sparkline";

type Props = {
  label: string;
  value: ReactNode;
  delta?: { text: string; tone: Tone };
  spark?: { points: number[]; label: string };
  hint?: string;
};

export function KpiCard({ label, value, delta, spark, hint }: Props) {
  return (
    <Card>
      <p className="text-sm font-semibold text-muted">{label}</p>
      <div className="mt-1 flex items-end justify-between gap-3">
        <p className="text-2xl font-bold break-words text-ink">{value}</p>
        {spark ? <Sparkline points={spark.points} label={spark.label} /> : null}
      </div>
      {delta ? (
        <div className="mt-2">
          <Badge tone={delta.tone}>{delta.text}</Badge>
        </div>
      ) : null}
      {hint ? <p className="mt-2 text-xs text-muted">{hint}</p> : null}
    </Card>
  );
}
