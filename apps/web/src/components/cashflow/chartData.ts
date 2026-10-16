import type { Day, Forecast } from "@/lib/api/cashflow";

export type ChartPoint = {
  on: string;
  /** plotting coordinate only; the exact server string is `closingText` */
  closing: number;
  closingText: string;
  below: boolean;
  cost: boolean;
};

/** A deal-linked outflow (milestone, duty, freight, …) happens on this day. */
export function hasDealCost(day: Day): boolean {
  return day.items.some((i) => i.direction === "OUT" && i.deal_ref !== null);
}

export function buildChartPoints(forecast: Forecast): ChartPoint[] {
  return forecast.daily.map((d) => ({
    on: d.on,
    closing: Number(d.closing),
    closingText: d.closing,
    below: d.below_buffer,
    cost: hasDealCost(d),
  }));
}

export type Range = { x1: string; x2: string };

/** Contiguous runs of days that close below the buffer. */
export function shortfallRanges(points: readonly ChartPoint[]): Range[] {
  const out: Range[] = [];
  let start: string | null = null;
  let prev: string | null = null;
  for (const p of points) {
    if (p.below && start === null) start = p.on;
    if (!p.below && start !== null && prev !== null) {
      out.push({ x1: start, x2: prev });
      start = null;
    }
    prev = p.on;
  }
  if (start !== null && prev !== null) out.push({ x1: start, x2: prev });
  return out;
}
