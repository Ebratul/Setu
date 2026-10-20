"use client";

import { useT, useLang } from "@/i18n";
import { getPrivacySummary } from "@/lib/api/privacy";
import { useApi } from "@/lib/useApi";
import { usePoll } from "@/lib/usePoll";

import { fmtNum } from "./privacyText";

type Props = {
  threadId?: string | null;
  /** Change this value to refetch immediately (e.g. after each chat turn). */
  refreshKey?: string | number;
  className?: string;
};

export function PrivacyCounter({ threadId = null, refreshKey = 0, className = "" }: Props) {
  const t = useT();
  const { lang } = useLang();
  const res = useApi((s) => getPrivacySummary(threadId, s), `privacy-summary|${threadId ?? ""}|${refreshKey}`);
  const { reload } = res;
  usePoll(reload, 15000);
  // keep showing the last good numbers during a refetch
  const data = res.data;
  if (!data) {
    return res.error ? (
      <p className={`text-xs text-muted ${className}`} data-testid="privacy-counter-unavailable">
        {t("privacy.counter.unavailable")}
      </p>
    ) : null;
  }
  const leaked = data.leaked > 0;
  return (
    <p
      aria-label={t("privacy.counter.label")}
      data-testid="privacy-counter"
      data-leaked={data.leaked}
      className={`flex flex-wrap items-center gap-x-2 text-xs font-semibold text-ink ${className}`}
    >
      <span>
        <span aria-hidden="true">🛡 </span>
        {t("privacy.counter.protected", { n: fmtNum(data.protected, lang) })}
      </span>
      <span aria-hidden="true">·</span>
      <span className={leaked ? "text-danger" : "text-success"} data-testid="privacy-counter-leaked">
        <span aria-hidden="true">{leaked ? "⚠ " : "✓ "}</span>
        {t("privacy.counter.leaked", { n: fmtNum(data.leaked, lang) })}
      </span>
    </p>
  );
}
