"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { QueryError } from "@/components/ui/QueryError";
import { KpiCard } from "@/components/analysis/KpiCard";
import { useLang, useT } from "@/i18n";
import {
  runScenario,
  type Forecast,
  type ScenarioRequest,
} from "@/lib/api/cashflow";
import { formatDate, formatMoney, type Currency } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/useApi";

import { AlertPanel } from "./AlertPanel";
import { CashflowAlerts } from "./CashflowAlerts";
import { CashflowCalendar } from "./CashflowCalendar";
import { CashflowChart } from "./CashflowChart";
import { DayDetails } from "./DayDetails";
import { WeeklyTable } from "./WeeklyTable";
import { WhatIfPanel } from "./WhatIfPanel";
import {
  buildScenarioRequest,
  initialWhatIf,
  type WhatIfState,
} from "./whatIf";

type Props = {
  forecast: Forecast;
  partyId?: string;
  initialDate: string | null;
};

export function CashflowLoaded({ forecast, partyId, initialDate }: Props) {
  const t = useT();
  const { lang } = useLang();
  const [whatIf, setWhatIf] = useState<WhatIfState | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  const state = whatIf ?? initialWhatIf(forecast);
  const built = useMemo(
    () => buildScenarioRequest(state, partyId),
    [state, partyId],
  );
  const key = useDebounced(JSON.stringify(built.request));
  const scenario = useApi(
    (s) => runScenario(JSON.parse(key) as ScenarioRequest, s),
    `scenario|${key}`,
    key !== "null",
  );

  const active = built.request !== null && scenario.data !== undefined;
  const shown = active && scenario.data ? scenario.data.forecast : forecast;
  const cur = shown.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);

  const selected = picked ?? initialDate;
  const day = shown.daily.find((d) => d.on === selected);
  const shortfall = shown.first_shortfall;

  return (
    <div className="space-y-6" aria-busy={scenario.loading ? true : undefined}>
      {active ? (
        <div role="status" className="flex flex-wrap items-center gap-3">
          <Badge tone="info" icon="◐">
            {t("whatif.badge")}
          </Badge>
          <span className="text-sm text-muted">{t("whatif.activeHint")}</span>
        </div>
      ) : null}

      <div
        role="status"
        className={`rounded-card border p-4 text-sm font-semibold ${
          shortfall
            ? "border-danger bg-danger-soft text-danger"
            : "border-success bg-success-soft text-success"
        }`}
      >
        {shortfall
          ? `▼ ${t("cf.firstShortfall", {
              amount: money(shortfall.amount),
              date: formatDate(shortfall.on, lang),
            })}`
          : `✓ ${t("cf.noShortfall", { days: 90 })}`}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label={t("cf.kpi.opening")}
          value={money(shown.opening_balance)}
        />
        <KpiCard
          label={t("cf.kpi.lowest")}
          value={money(shown.lowest_balance)}
          hint={t("cf.kpi.lowestOn", {
            date: formatDate(shown.lowest_on, lang),
          })}
        />
        <KpiCard label={t("cf.kpi.inflow")} value={money(shown.total_inflow)} />
        <KpiCard
          label={t("cf.kpi.outflow")}
          value={money(shown.total_outflow)}
        />
      </div>

      <Card as="section" labelledBy="chart-h">
        <h2 id="chart-h" className="mb-3 text-lg font-semibold text-ink">
          {t("cf.chartTitle")}
        </h2>
        <CashflowChart forecast={shown} />
        <WeeklyTable forecast={shown} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card as="section" labelledBy="cal-h" className="min-w-0">
          <h2 id="cal-h" className="text-lg font-semibold text-ink">
            {t("cf.calendarTitle")}
          </h2>
          <p className="mb-3 text-sm text-muted">{t("cf.calendarHint")}</p>
          <CashflowCalendar
            forecast={shown}
            selected={day?.on ?? null}
            onSelect={setPicked}
          />
        </Card>
        <DayDetails day={day} currency={cur} />
      </div>

      <WhatIfPanel
        forecast={forecast}
        state={state}
        errors={built.errors}
        active={active}
        loading={scenario.loading}
        onChange={setWhatIf}
        onReset={() => setWhatIf(null)}
      />
      {scenario.error ? (
        <QueryError error={scenario.error} onRetry={scenario.reload} />
      ) : null}

      {active && scenario.data ? (
        <Card as="section" labelledBy="sc-alerts-h" className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="sc-alerts-h" className="text-lg font-semibold text-ink">
              {t("whatif.alerts")}
            </h2>
            <Badge tone="info" icon="◐">
              {t("whatif.badge")}
            </Badge>
          </div>
          <AlertPanel
            alerts={scenario.data.alerts}
            emptyTitle={t("whatif.noAlerts")}
          />
        </Card>
      ) : null}

      <CashflowAlerts partyId={partyId} />
    </div>
  );
}
