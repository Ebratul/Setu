"use client";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { Tooltip } from "@/components/ui/Tooltip";
import { useLang, useT } from "@/i18n";
import { METRIC_IDS } from "@/lib/evalMetrics";
import type { EvalResults, Metric } from "@/lib/evalResults";

import { Section } from "./Section";

function MetricValue({ metric }: { metric: Metric }) {
  const { lang } = useLang();
  const t = useT();
  if (metric.unit === "percent") {
    return <>{new Intl.NumberFormat(lang, { style: "percent", maximumFractionDigits: 1 }).format(metric.value)}</>;
  }
  const nf = new Intl.NumberFormat(lang);
  return <>{t("landing.results.countOf", { value: nf.format(metric.value), total: nf.format(metric.total) })}</>;
}

export function ResultsGrid({ results }: { results: EvalResults }) {
  const t = useT();
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {METRIC_IDS.map((id) => {
        const m = results.metrics[id];
        return (
          <li key={id} className="min-w-0" data-testid={`metric-${id}`}>
            <Card className="h-full">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold text-muted">{t(`landing.results.${id}`)}</p>
                <Tooltip
                  label={
                    m
                      ? t(`landing.results.how.${id}`, { n: m.total, split: results.split })
                      : t("landing.results.howSoon")
                  }
                />
              </div>
              {m ? (
                <>
                  <p className="mt-2 text-3xl font-extrabold text-ink">
                    <MetricValue metric={m} />
                  </p>
                  <div className="mt-2">
                    <Badge tone="info">{t("landing.results.devBadge", { n: m.total })}</Badge>
                  </div>
                </>
              ) : (
                <p className="mt-2 text-lg font-bold text-muted">{t("landing.results.soon")}</p>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

export function ResultsNotes() {
  const t = useT();
  return (
    <div className="mt-4 grid gap-1 text-xs text-muted">
      <p className="flex items-start gap-2">
        <Icon name="info" size={14} className="mt-0.5 shrink-0" />
        {t("landing.results.caveat")}
      </p>
      <p className="ps-6">{t("landing.results.noTest")}</p>
    </div>
  );
}

export function ResultsBand({ results }: { results: EvalResults | null }) {
  const t = useT();
  return (
    <Section id="results" title={t("landing.results.title")} lead={t("landing.results.lead")}>
      {results ? (
        <>
          <ResultsGrid results={results} />
          <ResultsNotes />
        </>
      ) : (
        <Card>
          <p className="text-xl font-bold text-ink">{t("landing.results.soon")}</p>
          <p className="mt-2 text-sm text-muted">{t("landing.results.soonBody")}</p>
        </Card>
      )}
    </Section>
  );
}
