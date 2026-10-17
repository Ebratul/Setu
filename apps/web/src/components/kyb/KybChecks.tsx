"use client";

import { hasKey, useLang, useT } from "@/i18n";
import type { KybCheck } from "@/lib/api/kyb";

const ICON = { PASS: "✓", WARN: "▲", FAIL: "✕" } as const;
const COLOR = {
  PASS: "text-success",
  WARN: "text-warning",
  FAIL: "text-danger",
} as const;

function Evidence({ evidence }: { evidence: Record<string, unknown> }) {
  const t = useT();
  const entries = Object.entries(evidence);
  return (
    <details className="mt-1 text-xs">
      <summary className="cursor-pointer rounded font-semibold text-brand-700 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none">
        {t("sup.evidence")}
      </summary>
      {entries.length === 0 ? (
        <p className="mt-1 text-muted">{t("sup.noEvidence")}</p>
      ) : (
        <dl className="mt-1 grid gap-x-3 gap-y-1 sm:grid-cols-[max-content_1fr]">
          {entries.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className="break-words text-ink">
                {typeof v === "string" ? v : JSON.stringify(v)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </details>
  );
}

type Props = { checks: KybCheck[]; label: string };

export function KybChecks({ checks, label }: Props) {
  const t = useT();
  const { lang } = useLang();
  return (
    <ul aria-label={label} className="divide-y divide-line">
      {checks.map((c) => {
        const key = `kyb.code.${c.code}`;
        return (
          <li
            key={c.code}
            data-testid="kyb-check"
            data-status={c.status}
            className="flex gap-3 py-3"
          >
            <span
              aria-hidden="true"
              className={`mt-0.5 text-base font-bold ${COLOR[c.status]}`}
            >
              {ICON[c.status]}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">
                {hasKey(key) ? t(key) : c.code}{" "}
                <span className={`text-xs font-bold ${COLOR[c.status]}`}>
                  {t(`kyb.check.${c.status}`)}
                </span>
              </p>
              <p className="text-sm text-ink">
                {lang === "bn" ? c.detail_bn : c.detail_en}
              </p>
              <Evidence evidence={c.evidence} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
