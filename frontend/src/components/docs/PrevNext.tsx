"use client";

import Link from "next/link";

import { useT } from "@/i18n";

type Item = { href: string; title: string };

export function PrevNext({ prev, next }: { prev?: Item; next?: Item }) {
  const t = useT();
  if (!prev && !next) return null;
  const box =
    "block min-h-11 rounded-card border border-line p-4 hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none";
  return (
    <nav aria-label={t("docs.pager")} className="no-print mt-10 grid gap-3 sm:grid-cols-2">
      {prev ? (
        <Link href={prev.href} rel="prev" data-testid="docs-prev" className={box}>
          <span className="text-xs text-muted">← {t("docs.prev")}</span>
          <span className="block font-semibold text-brand-text">{prev.title}</span>
        </Link>
      ) : (
        <span />
      )}
      {next ? (
        <Link href={next.href} rel="next" data-testid="docs-next" className={`${box} text-right`}>
          <span className="text-xs text-muted">{t("docs.next")} →</span>
          <span className="block font-semibold text-brand-text">{next.title}</span>
        </Link>
      ) : null}
    </nav>
  );
}
