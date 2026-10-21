"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { useT } from "@/i18n";
import type { DocLang } from "@/lib/docs/types";

type Props = { lang: DocLang; fellBack: boolean; updated: string; guide?: string; roles: ReactNode[] };

export function DocMetaBar({ lang, fellBack, updated, guide, roles }: Props) {
  const t = useT();
  return (
    <div className="mt-4 space-y-3">
      {fellBack ? (
        <p role="status" className="rounded-card border border-warning bg-warning-soft p-3 text-sm text-ink">
          {t("docs.notTranslated")}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted">
        <span className="flex flex-wrap">{roles}</span>
        {updated ? <span>{t("docs.updated", { date: updated })}</span> : null}
        <button
          type="button"
          onClick={() => window.print()}
          className="no-print inline-flex min-h-9 items-center rounded font-semibold text-brand-text underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          {t("docs.print")}
        </button>
        {guide ? (
          <Link
            href={`/docs/${lang}/guide/${guide}`}
            data-testid="docs-download-pdf"
            className="no-print inline-flex min-h-9 items-center rounded font-semibold text-brand-text underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
          >
            {t("docs.downloadPdf")}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
