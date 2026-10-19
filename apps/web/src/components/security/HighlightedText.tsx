"use client";

import { useT } from "@/i18n";

type Range = { start: number; end: number; rule: string };
type Props = { text: string; highlights: readonly Range[]; className?: string };

type Piece = { text: string; rule: string | null };

/** Clamp to the text, drop empty ranges, and cut overlaps so pieces never repeat characters. */
export function splitHighlights(text: string, highlights: readonly Range[]): Piece[] {
  const ranges = highlights
    .map((h) => ({ rule: h.rule, start: Math.max(0, Math.min(text.length, h.start)), end: Math.max(0, Math.min(text.length, h.end)) }))
    .filter((h) => h.end > h.start)
    .sort((a, b) => a.start - b.start || b.end - a.end);
  const out: Piece[] = [];
  let pos = 0;
  for (const r of ranges) {
    const start = Math.max(r.start, pos);
    if (r.end <= start) continue;
    if (start > pos) out.push({ text: text.slice(pos, start), rule: null });
    out.push({ text: text.slice(start, r.end), rule: r.rule });
    pos = r.end;
  }
  if (pos < text.length) out.push({ text: text.slice(pos), rule: null });
  return out;
}

/** Untrusted text rendered inert (React text nodes only) with matched ranges in <mark>. */
export function HighlightedText({ text, highlights, className = "" }: Props) {
  const t = useT();
  const pieces = splitHighlights(text, highlights);
  return (
    <p
      data-testid="highlighted-text"
      className={`rounded-xl border border-line bg-surface-alt p-3 font-mono text-sm break-words whitespace-pre-wrap text-ink ${className}`}
    >
      {pieces.map((p, i) =>
        p.rule ? (
          <mark
            key={i}
            data-rule={p.rule}
            className="rounded-sm border-b-2 border-danger bg-danger-soft px-0.5 text-ink"
          >
            <span className="sr-only">{t("sec.hl.start", { rule: p.rule })} </span>
            {p.text}
            <span className="sr-only"> {t("sec.hl.end")}</span>
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </p>
  );
}

export function RuleChips({ rules }: { rules: readonly string[] }) {
  if (rules.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" data-testid="rule-chips">
      {rules.map((r) => (
        <li
          key={r}
          className="rounded-full border border-danger bg-danger-soft px-2 py-0.5 font-mono text-xs font-semibold text-danger"
        >
          {r}
        </li>
      ))}
    </ul>
  );
}
