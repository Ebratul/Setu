"use client";

import Link from "next/link";

import { useT } from "@/i18n";
import type { DocLang, DocSection } from "@/lib/docs/types";

type Props = { lang: DocLang; section: DocSection; title: string };

export function Breadcrumbs({ lang, section, title }: Props) {
  const t = useT();
  const link = "rounded text-brand-text underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none";
  return (
    <nav aria-label={t("docs.crumbs")} className="no-print mb-4 text-sm text-muted">
      <ol className="flex flex-wrap items-center gap-1">
        <li>
          <Link href={`/docs/${lang}`} className={link}>
            {t("docs.home")}
          </Link>
        </li>
        <li aria-hidden="true">›</li>
        <li>{t(`docs.section.${section}`)}</li>
        <li aria-hidden="true">›</li>
        <li aria-current="page" className="font-semibold text-ink">
          {title}
        </li>
      </ol>
    </nav>
  );
}
