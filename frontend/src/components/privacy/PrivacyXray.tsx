"use client";

import { QueryError } from "@/components/ui/QueryError";
import { Skeleton } from "@/components/ui/Skeleton";
import { useLang, useT } from "@/i18n";
import { getPrivacyDocument, getPrivacyMessage } from "@/lib/api/privacy";
import type { PrivacyXrayData } from "@/lib/privacy/types";
import { useApi } from "@/lib/useApi";

import { PrivacyBadge } from "./PrivacyBadge";
import { countsLine } from "./privacyText";
import { SegmentText } from "./SegmentText";

export function PrivacyXrayView({ data }: { data: PrivacyXrayData }) {
  const t = useT();
  const { lang } = useLang();
  if (!data.available) {
    return (
      <p className="text-sm text-muted" data-testid="xray-unavailable">
        {t("privacy.xray.unavailable")}
      </p>
    );
  }
  const { stats } = data;
  return (
    <div className="space-y-4" data-testid="xray">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-ink" data-testid="xray-summary">
          {countsLine(t, lang, stats.masked_by_type, stats.protected)}
        </p>
        <PrivacyBadge kind="leaked" count={stats.leaked_count} />
      </div>
      <p className="text-sm text-muted">{t("privacy.xray.intro")}</p>
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="xray-left-h" className="min-w-0 space-y-2">
          <h3 id="xray-left-h" className="text-sm font-bold text-ink">
            {t("privacy.xray.left")}
          </h3>
          {data.left.map((l, i) => (
            <div key={i} className="rounded-xl border border-line bg-surface-alt p-3 text-sm text-ink" data-testid="xray-left">
              {l.label ? <p className="mb-1 text-xs font-semibold text-muted">{l.label}</p> : null}
              <SegmentText segments={l.segments} />
            </div>
          ))}
        </section>
        <section aria-labelledby="xray-right-h" className="min-w-0 space-y-2">
          <h3 id="xray-right-h" className="text-sm font-bold text-ink">
            {t("privacy.xray.right")}
          </h3>
          {data.right.length === 0 ? <p className="text-sm text-muted">{t("privacy.xray.noCalls")}</p> : null}
          {data.right.map((r, i) => (
            <div key={i} className="rounded-xl border border-line bg-surface-alt p-3 text-sm text-ink" data-testid="xray-right">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-xs font-semibold text-muted">
                <span>{r.label || r.node}</span>
                {r.model ? <span>{t("privacy.model", { model: r.model })}</span> : null}
                {r.sent ? null : <PrivacyBadge kind="notSent" />}
              </div>
              <SegmentText segments={r.segments} mono />
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

type Props = { kind: "message" | "document"; id: string };

/** Fetches the transparency record lazily (mounted only when the dialog is open). */
export function PrivacyXray({ kind, id }: Props) {
  const t = useT();
  const res = useApi(
    (s) => (kind === "message" ? getPrivacyMessage(id, s) : getPrivacyDocument(id, s)),
    `privacy-xray|${kind}|${id}`,
  );
  if (res.error) return <QueryError error={res.error} onRetry={res.reload} />;
  if (!res.data)
    return (
      <div aria-busy="true" role="status">
        <span className="sr-only">{t("privacy.xray.loading")}</span>
        <Skeleton className="h-32" />
      </div>
    );
  return <PrivacyXrayView data={res.data} />;
}
