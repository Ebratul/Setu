"use client";

import { useLang, useT } from "@/i18n";
import type { FindingOut } from "@/lib/api/documents";

import { fieldValue } from "./mismatch";
import { findingLabel } from "./reasons";

const META: Record<FindingOut["status"], { icon: string; cls: string }> = {
  PASS: { icon: "✓", cls: "text-success" },
  WARN: { icon: "▲", cls: "text-warning" },
  FAIL: { icon: "✕", cls: "text-danger" },
  SKIPPED: { icon: "–", cls: "text-muted" },
};

/** Evidence as key/value pairs rendered as plain text. */
function Evidence({ detail }: { detail: Record<string, unknown> }) {
  const entries = Object.entries(detail);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-2 grid gap-x-3 gap-y-1 rounded-lg bg-surface-alt p-2 text-xs sm:grid-cols-[auto_1fr]">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-medium text-muted">{k}</dt>
          <dd className="font-mono break-words whitespace-pre-wrap text-ink">
            {typeof v === "object" && v !== null ? JSON.stringify(v, null, 1) : fieldValue(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ChecksList({ findings }: { findings: readonly FindingOut[] }) {
  const t = useT();
  const { lang } = useLang();
  if (findings.length === 0) return <p className="text-sm text-muted">{t("doc.checks.none")}</p>;
  return (
    <ul className="divide-y divide-line" data-testid="checks-list">
      {findings.map((f) => {
        const m = META[f.status];
        return (
          <li key={f.check_code} data-testid="check" data-status={f.status} className="py-2">
            <details>
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 rounded-md text-sm focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
                <span aria-hidden="true" className={`font-bold ${m.cls}`}>
                  {m.icon}
                </span>
                <span className="font-semibold text-ink">{findingLabel(f, lang)}</span>
                <span className={`text-xs font-semibold ${m.cls}`}>{t(`doc.check.${f.status}`)}</span>
              </summary>
              {f.status === "WARN" || f.status === "FAIL" ? (
                <p className="mt-1 text-sm text-ink" data-testid="check-issue">
                  {lang === "bn" ? f.issue_bn : f.issue_en}
                </p>
              ) : null}
              <Evidence detail={f.detail} />
            </details>
          </li>
        );
      })}
    </ul>
  );
}
