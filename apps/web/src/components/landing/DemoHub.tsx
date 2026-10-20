"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";
import type { EvalResults } from "@/lib/evalResults";

import { ButtonLink } from "./ButtonLink";
import { FEATURES } from "./Features";
import { PublicFooter } from "./PublicFooter";
import { PublicHeader } from "./PublicHeader";
import { ResultsGrid, ResultsNotes } from "./ResultsBand";

export const DEMO_TARGETS: { id: string; href: string }[] = [
  { id: "financing", href: "/app/financing" },
  { id: "cashflow", href: "/app/cashflow" },
  { id: "analysis", href: "/app/analysis" },
  { id: "forensics", href: "/demo/attack-console" },
  { id: "risk", href: "/demo/risk-playground" },
  { id: "cny", href: "/app/deals" },
  { id: "chat", href: "/app/chat" },
];

const JUDGE_LINKS = [
  { id: "risk", href: "/demo/risk-playground" },
  { id: "privacy", href: "/demo/privacy-playground" },
  { id: "injection", href: "/demo/attack-console" },
  { id: "verify", href: "/verify" },
  { id: "audit", href: "/app/admin/audit" },
] as const;

const link =
  "inline-flex min-h-11 items-center gap-1 rounded-lg font-semibold text-brand-text hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

type Props = { results: EvalResults | null; embedded?: boolean };

/** Lightweight hub; `embedded` renders only the scorecard and step list (no page chrome or h1). */
export function DemoHub({ results, embedded = false }: Props) {
  const t = useT();
  const params = useSearchParams();
  const judge = params.get("judge") === "1";
  const stepParam = Number(params.get("step"));
  const step = Number.isInteger(stepParam) && stepParam >= 1 && stepParam <= DEMO_TARGETS.length ? stepParam : null;

  useEffect(() => {
    if (step) document.getElementById(`step-${step}`)?.scrollIntoView({ block: "center" });
  }, [step]);

  const body = (
    <>
      {judge ? (
        <section aria-labelledby="judge-title" className="mt-8 rounded-hero border border-brand-700 bg-brand-50 p-5">
          <h2 id="judge-title" className="text-xl font-bold text-ink">
            {t("landing.demo.judgeTitle")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("landing.demo.judgeLead")}</p>
          <ul className="mt-4 flex flex-wrap gap-x-6">
            {JUDGE_LINKS.map((j) => (
              <li key={j.id}>
                <Link href={j.href} className={link}>
                  {t(`landing.demo.judge.${j.id}`)}
                  <Icon name="arrow" size={16} className="rtl:rotate-180" />
                </Link>
              </li>
            ))}
          </ul>
          <h3 className="mt-5 text-base font-bold text-ink">{t("landing.demo.judgeResults")}</h3>
          <div className="mt-3">
            {results ? (
              <>
                <ResultsGrid results={results} />
                <ResultsNotes />
              </>
            ) : (
              <p className="text-sm font-semibold text-muted">{t("landing.results.soon")}</p>
            )}
          </div>
        </section>
      ) : null}

      <ol className="mt-8 grid gap-4" aria-label={t("landing.demo.stepsLabel")}>
        {DEMO_TARGETS.map((s, i) => {
          const n = i + 1;
          const f = FEATURES[i];
          const current = step === n;
          return (
            <li key={s.id} id={`step-${n}`} aria-current={current ? "step" : undefined} className="scroll-mt-24">
              <Card className={current ? "ring-2 ring-brand-700" : ""}>
                <div className="flex flex-wrap items-start gap-4">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-700 font-bold text-white">
                    {n}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="flex flex-wrap items-center gap-2 text-lg font-bold text-ink">
                      <Icon name={f.icon} size={18} />
                      {t(`landing.features.${s.id}.name`)}
                      {current ? <Badge tone="info">{t("landing.demo.here")}</Badge> : null}
                    </h3>
                    <p className="mt-1 text-sm text-muted">{t(`landing.demo.step.${s.id}`)}</p>
                    <p className="mt-1 text-xs text-muted">{t("landing.demo.signIn")}</p>
                  </div>
                  <ButtonLink href={s.href} variant={current ? "accent" : "secondary"}>
                    {t("landing.demo.open")}
                  </ButtonLink>
                </div>
              </Card>
            </li>
          );
        })}
      </ol>
    </>
  );

  if (embedded) return body;
  return (
    <>
      <PublicHeader />
      <main id="main" className="mx-auto w-full max-w-4xl flex-1 px-4 py-10 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-extrabold tracking-tight text-ink">{t("landing.demo.title")}</h1>
          <SimulatedBadge />
        </div>
        <p className="mt-3 text-base text-muted">{t("landing.demo.lead")}</p>
        {body}
      </main>
      <PublicFooter />
    </>
  );
}
