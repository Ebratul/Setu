"use client";

import { useLang, useT } from "@/i18n";
import type { Day, Forecast } from "@/lib/api/cashflow";
import {
  formatDate,
  formatDay,
  formatMoney,
  formatSigned,
  type Currency,
} from "@/lib/format";

import { hasDealCost } from "./chartData";

type Props = {
  forecast: Forecast;
  selected: string | null;
  onSelect: (on: string) => void;
};

export function CashflowCalendar({ forecast, selected, onSelect }: Props) {
  const t = useT();
  const { lang } = useLang();
  const cur = forecast.currency as Currency;
  return (
    <div className="space-y-3">
      {forecast.weekly.map((w) => {
        const days = forecast.daily.filter(
          (d) => d.on >= w.start && d.on <= w.end,
        );
        return (
          <section
            key={w.start}
            aria-label={t("cf.weekOf", {
              start: formatDate(w.start, lang),
              end: formatDate(w.end, lang),
            })}
          >
            <h4 className="mb-1 text-xs font-semibold text-muted">
              {formatDay(w.start, lang)} – {formatDay(w.end, lang)}
            </h4>
            <div className="overflow-x-auto pb-1">
              <ul className="grid min-w-168 grid-cols-7 gap-1">
                {days.map((d) => (
                  <li key={d.on}>
                    <DayCell
                      day={d}
                      cur={cur}
                      selected={selected === d.on}
                      onSelect={onSelect}
                    />
                  </li>
                ))}
              </ul>
            </div>
          </section>
        );
      })}
    </div>
  );
}

type CellProps = {
  day: Day;
  cur: Currency;
  selected: boolean;
  onSelect: (on: string) => void;
};

function DayCell({ day, cur, selected, onSelect }: CellProps) {
  const t = useT();
  const { lang } = useLang();
  const cost = hasDealCost(day);
  const label = t("cf.dayLabel", {
    date: formatDate(day.on, lang),
    closing: formatMoney(day.closing, cur, lang),
    net: formatSigned(day.net, lang),
  });
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={day.below_buffer ? `${label}. ${t("cf.belowBuffer")}` : label}
      onClick={() => onSelect(day.on)}
      className={`flex h-full w-full flex-col gap-0.5 rounded-lg border p-2 text-left text-xs focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
        day.below_buffer
          ? "border-danger bg-danger-soft"
          : "border-line bg-surface hover:bg-brand-50"
      } ${selected ? "ring-2 ring-brand-700" : ""}`}
    >
      <span className="font-semibold text-ink">{formatDay(day.on, lang)}</span>
      <span className="font-semibold text-ink tabular-nums">
        {formatMoney(day.closing, cur, lang)}
      </span>
      <span className="text-muted tabular-nums">
        {formatSigned(day.net, lang)}
      </span>
      {day.below_buffer ? (
        <span className="font-semibold text-danger">▼ {t("cf.low")}</span>
      ) : null}
      {cost ? (
        <span className="text-warning">◆ {t("cf.dealCostShort")}</span>
      ) : null}
    </button>
  );
}
