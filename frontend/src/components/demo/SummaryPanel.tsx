"use client";

import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { ButtonLink } from "@/components/landing/ButtonLink";
import { Icon } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useLang, useT } from "@/i18n";
import type { DemoSummary } from "@/lib/api/demo";

import { biText, toDemoLang } from "./demoModel";

type Props = { summary: DemoSummary | null; onBack: () => void; onExplore: () => void };

/** "What you just saw": the five key numbers, the attacks blocked and where to dig deeper. */
export function SummaryPanel({ summary, onBack, onExplore }: Props) {
  const t = useT();
  const lang = toDemoLang(useLang().lang);
  return (
    <section aria-labelledby="demo-summary-h" data-testid="summary" className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="demo-summary-h" className="text-xl font-extrabold text-ink">
          {t("demo.summary.title")}
        </h2>
        <SimulatedBadge />
      </div>
      {!summary ? (
        <p role="status" className="text-sm text-muted">
          {t("common.loading")}
        </p>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-2">
            {summary.numbers.map((n) => (
              <li key={n.key} data-summary={n.key} className="rounded-xl border border-line bg-surface-alt p-3">
                <p className="text-xl font-extrabold break-words text-ink">{n.value}</p>
                <p className="text-xs font-semibold text-muted">{biText(n.label, lang)}</p>
              </li>
            ))}
          </ul>
          <div>
            <h3 className="text-sm font-bold text-ink">{t("demo.summary.attacks")}</h3>
            <ul className="mt-1 space-y-1">
              {summary.attacks.map((a, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-ink">
                  <Icon name="shield" size={16} className="mt-0.5 shrink-0 text-danger" />
                  {biText(a, lang)}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-bold text-ink">{t("demo.summary.dig")}</h3>
            <ul className="mt-1 flex flex-wrap gap-x-4">
              {summary.links.map((l) => (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    target="_blank"
                    rel="noopener"
                    className="inline-flex min-h-11 items-center gap-1 rounded-lg text-sm font-semibold text-brand-text hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                  >
                    {biText(l.label, lang)}
                    <Icon name="external" size={14} />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="accent" onClick={onExplore}>
          {t("demo.summary.explore")}
        </Button>
        <Button variant="secondary" onClick={onBack}>
          {t("demo.summary.back")}
        </Button>
        <ButtonLink href="/demo" variant="ghost">
          {t("demo.summary.hub")}
        </ButtonLink>
      </div>
    </section>
  );
}
