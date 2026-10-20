"use client";

import Link from "next/link";
import { useId, type ReactNode } from "react";

import { Badge } from "@/components/ui/Badge";
import { useLang, useT } from "@/i18n";
import { safeAppHref } from "../markdown";

type Props = {
  type: string;
  title: string;
  explanationEn: string;
  explanationBn: string;
  children: ReactNode;
  linkHref?: string | null;
  linkLabel?: string;
};

/** Common frame: title, Simulated tag, explanation in the UI language, optional internal link. */
export function CardShell({
  type,
  title,
  explanationEn,
  explanationBn,
  children,
  linkHref,
  linkLabel,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const id = useId();
  const href = safeAppHref(linkHref);
  return (
    <article
      data-card-type={type}
      aria-labelledby={id}
      className="min-w-0 space-y-3 rounded-2xl border border-line bg-surface p-3 shadow-card sm:p-4"
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-bold text-ink">
          {title}
        </h3>
        <Badge tone="warning" icon="◇">
          {t("common.simulatedData")}
        </Badge>
      </header>
      <p className="text-sm text-ink">
        {lang === "bn" ? explanationBn : explanationEn}
      </p>
      {children}
      {href && linkLabel ? (
        <Link
          href={href}
          className="inline-block rounded-md text-sm font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          {linkLabel} <span aria-hidden="true">→</span>
        </Link>
      ) : null}
    </article>
  );
}

type KpiProps = { label: string; value: ReactNode; tone?: "default" | "danger" };

export function Kpi({ label, value, tone = "default" }: KpiProps) {
  return (
    <div className="min-w-0 rounded-xl bg-surface-alt p-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd
        className={`text-base font-bold break-words ${tone === "danger" ? "text-danger" : "text-ink"}`}
      >
        {value}
      </dd>
    </div>
  );
}
