"use client";

import { useLang, useT } from "@/i18n";
import type { FxRate } from "@/lib/api/analysis";
import { formatDate } from "@/lib/format";

type Props = { fx: FxRate[] };

export function FxNote({ fx }: Props) {
  const t = useT();
  const { lang } = useLang();
  if (fx.length === 0) return null;
  const asOf = formatDate(fx[0].as_of, lang);
  return (
    <p className="text-xs text-muted">
      <strong>{t("common.simulatedData")}.</strong>{" "}
      {t("analysis.fx.note", { date: asOf })}{" "}
      {fx.map((r) => `1 ${r.base} = ${r.rate} ${r.quote}`).join(" · ")}
    </p>
  );
}
