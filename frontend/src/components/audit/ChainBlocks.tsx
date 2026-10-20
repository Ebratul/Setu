"use client";

import { TierBadge } from "@/components/risk/TierBadge";
import { useT } from "@/i18n";

import { shortHash } from "./auditText";

export type BlockEntry = { seq: number; action: string; tier: number; decision: string; entry_hash: string };

type Props = {
  entries: readonly BlockEntry[];
  /** Blocks from this seq onward are drawn red (tamper view). */
  brokenFrom?: number | null;
  /** A seq that should have been here but is not (deleted entry). */
  missingSeq?: number | null;
  /** Colour every block green/red (tamper view); otherwise blocks are neutral. */
  judge?: boolean;
  newSeqs?: ReadonlySet<number>;
  selected?: number | null;
  onSelect?: (seq: number) => void;
  label: string;
};

const focus = "focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";

function Link() {
  return <span aria-hidden="true" className="h-0.5 w-6 shrink-0 self-center bg-line" />;
}

export function ChainBlocks({ entries, brokenFrom = null, missingSeq = null, judge = false, newSeqs, selected, onSelect, label }: Props) {
  const t = useT();
  const items: ({ kind: "entry"; e: BlockEntry } | { kind: "gap"; seq: number })[] = [];
  let gapDone = missingSeq == null;
  for (const e of entries) {
    if (!gapDone && missingSeq != null && e.seq > missingSeq) {
      items.push({ kind: "gap", seq: missingSeq });
      gapDone = true;
    }
    items.push({ kind: "entry", e });
  }
  return (
    <div className="overflow-x-auto pb-2" tabIndex={0} role="region" aria-label={label}>
      <ol className="flex w-max items-stretch px-1 py-2" data-testid="chain-blocks">
        {items.map((it, i) => (
          <li key={it.kind === "gap" ? `gap-${it.seq}` : it.e.seq} className="flex">
            {i > 0 ? <Link /> : null}
            {it.kind === "gap" ? (
              <div
                data-testid="chain-gap"
                className="flex w-36 flex-col justify-center rounded-xl border-2 border-dashed border-danger bg-danger-soft p-3 text-xs font-semibold text-danger"
              >
                <span aria-hidden="true">✕ </span>
                {t("audit.chain.missing", { seq: it.seq })}
              </div>
            ) : (
              <Block
                e={it.e}
                broken={brokenFrom != null && it.e.seq >= brokenFrom}
                judged={judge}
                isNew={newSeqs?.has(it.e.seq) ?? false}
                selected={selected === it.e.seq}
                onSelect={onSelect}
              />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Block({
  e,
  broken,
  judged,
  isNew,
  selected,
  onSelect,
}: {
  e: BlockEntry;
  broken: boolean;
  judged: boolean;
  isNew: boolean;
  selected: boolean;
  onSelect?: (seq: number) => void;
}) {
  const t = useT();
  const tone = broken ? "border-danger bg-danger-soft" : judged ? "border-success bg-success-soft" : "border-line bg-surface";
  return (
    <button
      type="button"
      data-testid="chain-block"
      data-seq={e.seq}
      data-state={broken ? "broken" : judged ? "ok" : "plain"}
      aria-pressed={selected}
      aria-label={t("audit.chain.blockLabel", { seq: e.seq, action: e.action })}
      onClick={() => onSelect?.(e.seq)}
      className={`flex w-40 shrink-0 flex-col gap-1.5 rounded-xl border-2 p-3 text-left shadow-card hover:shadow-card-hover ${tone} ${isNew ? "audit-new" : ""} ${selected ? "ring-2 ring-brand-500" : ""} ${focus}`}
    >
      <span className="flex items-center justify-between text-xs font-bold text-ink">
        <span>#{e.seq}</span>
        {broken ? (
          <span className="text-danger">
            <span aria-hidden="true">✕ </span>
            {t("audit.chain.broken")}
          </span>
        ) : judged ? (
          <span className="text-success">
            <span aria-hidden="true">✓ </span>
            {t("audit.chain.intact")}
          </span>
        ) : null}
      </span>
      <span className="text-sm font-semibold break-words text-ink">{e.action}</span>
      <TierBadge tier={e.tier} decision={e.decision} />
      <code className="font-mono text-xs text-muted" title={e.entry_hash}>
        {shortHash(e.entry_hash)}
      </code>
    </button>
  );
}
