"use client";

import { useT } from "@/i18n";

type Props = { section?: string; headingId?: string };

export function DocsHomeText({ section, headingId }: Props) {
  const t = useT();
  if (section) {
    return (
      <h2 id={headingId} className="text-lg font-bold text-ink">
        {t(`docs.section.${section}`)}
      </h2>
    );
  }
  return (
    <div>
      <h1 className="text-3xl font-bold text-ink">{t("docs.title")}</h1>
      <p className="mt-2 text-muted">{t("docs.lead")}</p>
    </div>
  );
}
