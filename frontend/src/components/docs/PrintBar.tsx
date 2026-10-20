"use client";

import { Button } from "@/components/ui/Button";
import { useT } from "@/i18n";

export function PrintBar({ role, lang }: { role: string; lang: string }) {
  const t = useT();
  return (
    <div className="no-print mb-6 flex flex-wrap items-center gap-3 rounded-card border border-line bg-surface p-4">
      <p className="flex-1 text-sm text-muted">
        <strong className="text-ink">{t(`docs.section.${role}`)}</strong> ({lang.toUpperCase()}) — {t("docs.downloadHint")}
      </p>
      <Button onClick={() => window.print()}>{t("docs.downloadPdf")}</Button>
    </div>
  );
}
