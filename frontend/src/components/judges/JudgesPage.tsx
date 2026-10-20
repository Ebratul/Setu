"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ButtonLink } from "@/components/landing/ButtonLink";
import { JudgeModeButton } from "@/components/landing/JudgeModeButton";
import { StatusPanel } from "@/components/status/StatusPanel";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { SimulatedBadge } from "@/components/ui/SimulatedBadge";
import { useT } from "@/i18n";

import { judgeConfig, SCORE_ROWS, TRY_ITEMS } from "./links";
import { QrSection } from "./QrSection";

const textLink =
  "inline-flex min-h-11 items-center gap-1 rounded-lg font-semibold text-brand-text underline underline-offset-2 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

function Block({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="scroll-mt-20 py-10"
    >
      <h2
        id={`${id}-title`}
        className="text-2xl font-bold tracking-tight text-ink"
      >
        {title}
      </h2>
      {lead ? <p className="mt-2 max-w-3xl text-muted">{lead}</p> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}

type Resource = {
  id: "docs" | "repo" | "video" | "status" | "site";
  url: string | null;
  inPage?: string;
};

export function JudgesPage() {
  const t = useT();
  const cfg = judgeConfig();
  const resources: Resource[] = [
    { id: "site", url: cfg.siteUrl },
    { id: "docs", url: cfg.docsUrl },
    { id: "repo", url: cfg.repoUrl },
    { id: "video", url: cfg.videoUrl },
    { id: "status", url: cfg.statusUrl, inPage: "#status" },
  ];

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6">
      <header className="grid gap-4 print:hidden">
        <SimulatedBadge />
        <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">
          {t("judges.title")}
        </h1>
        <p className="max-w-3xl text-lg text-muted">{t("judges.lead")}</p>
        <div className="flex flex-wrap items-start gap-3">
          <ButtonLink href="/demo" variant="accent">
            {t("judges.hero.demo")}
          </ButtonLink>
          <JudgeModeButton
            withSandbox
            label={t("judges.hero.sandbox")}
            busyLabel={t("judges.hero.sandboxBusy")}
          />
        </div>
        <p className="max-w-3xl text-sm text-muted">{t("judges.hero.note")}</p>
      </header>

      <Block
        id="signin"
        title={t("judges.creds.title")}
        lead={t("judges.creds.lead")}
      >
        <Card>
          <dl className="grid gap-3 text-sm">
            <div>
              <dt className="font-semibold text-ink">
                {t("judges.creds.email")}
              </dt>
              <dd className="font-mono text-ink" data-testid="judge-email">
                {cfg.email}
              </dd>
            </div>
            <div>
              <dt className="sr-only">{t("judges.creds.title")}</dt>
              <dd className="text-muted">{t("judges.creds.how")}</dd>
            </div>
            {cfg.note ? (
              <div>
                <dt className="font-semibold text-ink">
                  {t("judges.creds.noteLabel")}
                </dt>
                <dd className="text-muted" data-testid="judge-note">
                  {cfg.note}
                </dd>
              </div>
            ) : null}
          </dl>
          <Link href="/login" className={`${textLink} mt-2`}>
            {t("judges.creds.signin")}
          </Link>
        </Card>
      </Block>

      <Block id="try" title={t("judges.try.title")} lead={t("judges.try.lead")}>
        <ol className="grid gap-3">
          {TRY_ITEMS.map((item, i) => (
            <li
              key={item.id}
              className="flex gap-3 rounded-2xl border border-line bg-surface p-4"
            >
              <span
                aria-hidden="true"
                className="flex size-8 shrink-0 items-center justify-center rounded-full bg-brand-700 text-sm font-bold text-white"
              >
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="font-semibold text-ink">
                  {t(`judges.try.${item.id}.title`)}
                </p>
                <p className="text-sm text-muted">
                  {t(`judges.try.${item.id}.body`)}
                </p>
                <Link
                  href={item.href}
                  aria-label={`${t("judges.try.open")}: ${t(`judges.try.${item.id}.title`)}`}
                  className={textLink}
                >
                  {t("judges.try.open")}
                  <Icon name="arrow" size={14} />
                </Link>
              </div>
            </li>
          ))}
        </ol>
      </Block>

      <Block
        id="scorecard"
        title={t("judges.score.title")}
        lead={t("judges.score.lead")}
      >
        <p className="mb-4 text-sm text-muted">{t("judges.score.signin")}</p>
        <ul className="grid gap-3 sm:grid-cols-2">
          {SCORE_ROWS.map((row) => (
            <li
              key={row.id}
              className="grid gap-1 rounded-2xl border border-line bg-surface p-4"
              data-testid="score-row"
            >
              <p className="font-semibold text-ink">
                {t(`judges.score.${row.id}.req`)}
              </p>
              <p className="text-sm text-muted">
                {t("judges.score.where")}:{" "}
                <Link
                  href={row.href}
                  className={textLink.replace("min-h-11", "min-h-6")}
                >
                  {t(`judges.score.${row.id}.where`)}
                </Link>
              </p>
            </li>
          ))}
        </ul>
      </Block>

      <Block
        id="resources"
        title={t("judges.resources.title")}
        lead={t("judges.resources.lead")}
      >
        <ul className="grid gap-3 sm:grid-cols-2">
          {resources.map((r) => {
            const label = t(`judges.resources.${r.id}`);
            return (
              <li
                key={r.id}
                className="flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-surface p-4"
                data-testid={`resource-${r.id}`}
              >
                {r.url ? (
                  <a
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={textLink}
                  >
                    {label}
                    <span className="sr-only">
                      {" "}
                      {t("judges.resources.newTab")}
                    </span>
                    <Icon name="external" size={14} />
                  </a>
                ) : r.inPage ? (
                  <a href={r.inPage} className={textLink}>
                    {label}
                  </a>
                ) : (
                  <>
                    <span className="font-semibold text-ink">{label}</span>
                    <Badge
                      tone="neutral"
                      icon={<Icon name="clock" size={12} />}
                    >
                      {t("judges.resources.coming")}
                    </Badge>
                    <span className="sr-only">
                      {t("judges.resources.comingHint")}
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </Block>

      <QrSection />

      <Block
        id="status"
        title={t("judges.status.title")}
        lead={t("judges.status.lead")}
      >
        <StatusPanel />
      </Block>
    </div>
  );
}
