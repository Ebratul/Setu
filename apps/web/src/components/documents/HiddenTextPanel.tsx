"use client";

import { HighlightedText, RuleChips } from "@/components/security/HighlightedText";
import { useT } from "@/i18n";
import type { HiddenTextOut } from "@/lib/api/documents";

export function hasInstruction(h: HiddenTextOut): boolean {
  return Object.values(h.instruction_codes).some((c) => Array.isArray(c) && c.length > 0);
}

/** Hidden spans and instruction notice. Every string from the document is rendered as inert text. */
export function HiddenTextPanel({ hidden }: { hidden: HiddenTextOut }) {
  const t = useT();
  const instruction = hasInstruction(hidden);
  const sources = Object.entries(hidden.instruction_codes).filter(([, c]) => c.length > 0);
  return (
    <section
      aria-labelledby="hid-h"
      data-testid="hidden-panel"
      className="space-y-3 rounded-2xl border-2 border-danger bg-danger-soft p-4"
    >
      <h2 id="hid-h" className="text-base font-bold text-danger">
        <span aria-hidden="true">■ </span>
        {t("doc.hidden.title")}
      </h2>
      {instruction ? (
        <p role="alert" data-testid="hidden-notice" className="font-semibold text-ink">
          {t("doc.hidden.instruction")}
        </p>
      ) : null}
      {hidden.spans.length === 0 ? (
        <p className="text-sm text-ink">{t("doc.hidden.none")}</p>
      ) : (
        <ul className="space-y-2">
          {hidden.spans.map((s, i) => (
            <li key={i} data-testid="hidden-span" className="rounded-xl border border-danger bg-surface p-3">
              <p className="text-xs text-muted">
                {t("doc.hidden.page", { n: s.page })} · {t(`doc.hidden.reason.${s.reason}`)}
              </p>
              <pre className="mt-1 max-h-40 overflow-auto font-mono text-sm break-words whitespace-pre-wrap text-ink">
                {s.text}
              </pre>
            </li>
          ))}
        </ul>
      )}
      {(hidden.injection ?? []).map((f, i) => (
        <div key={i} data-testid="injection-block" className="space-y-2 rounded-xl border border-danger bg-surface p-3">
          <p className="text-sm font-bold text-danger">
            <span aria-hidden="true">⚠ </span>
            {t("sec.doc.detected", { rules: f.rules.join(", ") })}
          </p>
          <p className="text-xs text-muted">
            {t("sec.doc.where", { source: t(`sec.source.${f.source}`), score: f.score })}
          </p>
          <RuleChips rules={f.rules} />
          <HighlightedText text={f.text} highlights={f.highlights} />
        </div>
      ))}
      {sources.length > 0 ? (
        <p className="text-xs text-ink">
          {t("doc.hidden.sources", {
            list: sources.map(([src, codes]) => `${src}: ${codes.join(", ")}`).join("; "),
          })}
        </p>
      ) : null}
    </section>
  );
}
