"use client";

import Link from "next/link";
import { forwardRef } from "react";

import { useLang, useT } from "@/i18n";
import type { Citation } from "@/lib/api/chat";
import { formatDate } from "@/lib/format";

type Props = {
  citations: Citation[];
  idPrefix: string;
  highlighted: string | null;
};

export const sourceDomId = (prefix: string, citeId: string) =>
  `${prefix}-src-${citeId}`;

function safeDate(iso: string, lang: "en" | "bn" | "zh"): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? formatDate(iso, lang) : iso;
}

/** Plain-text source list; original_reference is never turned into a link. */
export const SourcesList = forwardRef<HTMLElement, Props>(function SourcesList(
  { citations, idPrefix, highlighted },
  ref,
) {
  const t = useT();
  const { lang } = useLang();
  if (citations.length === 0) return null;
  return (
    <section
      ref={ref}
      aria-label={t("chat.sources.title")}
      data-testid="sources"
      className="space-y-1.5 rounded-xl border border-line bg-surface-alt p-2.5"
    >
      <h4 className="text-xs font-bold text-ink">{t("chat.sources.title")}</h4>
      <ol className="space-y-2">
        {citations.map((c) => (
          <li
            key={c.cite_id}
            id={sourceDomId(idPrefix, c.cite_id)}
            tabIndex={-1}
            data-cite-entry={c.cite_id}
            data-highlighted={highlighted === c.cite_id}
            className={`space-y-0.5 rounded-lg p-1.5 text-xs text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${highlighted === c.cite_id ? "bg-brand-50 ring-2 ring-brand-600" : ""}`}
          >
            <p className="font-bold break-words">
              [{c.cite_id}] {c.title}
            </p>
            {c.heading_path ? (
              <p className="break-words text-muted">{c.heading_path}</p>
            ) : null}
            {c.guide_url ? (
              <Link
                href={c.guide_url}
                data-testid="open-guide"
                className="inline-flex min-h-11 items-center gap-1 rounded-md font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
              >
                {t("docs.openGuide")}
              </Link>
            ) : c.original_reference ? (
              <p className="break-words">{c.original_reference}</p>
            ) : null}
            <p className="text-muted">
              {t("chat.sources.reviewed", { date: safeDate(c.last_reviewed, lang) })}
            </p>
            {c.disclaimer && !c.guide_url ? (
              <p className="break-words text-muted italic">{c.disclaimer}</p>
            ) : null}
          </li>
        ))}
      </ol>
      <p className="text-xs font-semibold text-ink">{t("chat.sources.note")}</p>
    </section>
  );
});
