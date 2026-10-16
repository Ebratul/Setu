"use client";

import { Badge } from "@/components/ui/Badge";
import { hasKey, pickLang, useLang, useT } from "@/i18n";
import type { SupplierScore } from "@/lib/api/analysis";
import { formatDecimal, formatPct } from "@/lib/format";

type Props = { supplier: SupplierScore };

function ScoreBar({ score, weak }: { score: string | null; weak: boolean }) {
  const t = useT();
  const { lang } = useLang();
  if (score === null) return <span className="text-muted">—</span>;
  return (
    <div className="flex min-w-28 items-center gap-2">
      <div
        role="meter"
        aria-label={t("suppliers.col.score")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Number(score)}
        aria-valuetext={formatDecimal(score, lang, 2)}
        className="h-2 w-16 overflow-hidden rounded-full bg-line"
      >
        <div
          className={`h-full ${weak ? "bg-danger" : "bg-success"}`}
          style={{ width: `${Math.min(100, Math.max(0, Number(score)))}%` }}
        />
      </div>
      <span className="font-semibold tabular-nums">
        {formatDecimal(score, lang, 2)}
      </span>
    </div>
  );
}

export function SupplierRow({ supplier: s }: Props) {
  const t = useT();
  const { lang } = useLang();
  const kybKey = `kyb.${s.kyb_status}`;
  const verified = s.kyb_status === "VERIFIED";
  const pct = (v: string | null) => (v === null ? "—" : formatPct(v, lang));
  return (
    <tr
      data-weak={s.weak ? "true" : undefined}
      className={`border-b border-line align-top last:border-0 ${
        s.weak ? "bg-danger-soft" : ""
      }`}
    >
      <th scope="row" className="p-3 text-left">
        <div className="font-semibold text-ink">{s.name}</div>
        <div className="text-xs text-muted">
          {s.city}, {s.country}
        </div>
        {s.weak ? (
          <div className="mt-2 space-y-1">
            <Badge tone="danger" icon="⚠">
              {t("suppliers.weak")}
            </Badge>
            <ul className="list-disc space-y-0.5 pl-4 text-xs font-normal text-ink">
              {s.notes.map((n) => (
                <li key={n.code}>{pickLang(n, lang)}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </th>
      <td className="p-3">
        <Badge
          tone={verified ? "success" : "warning"}
          icon={verified ? "✓" : "⚠"}
        >
          {hasKey(kybKey) ? t(kybKey) : s.kyb_status}
        </Badge>
      </td>
      <td className="p-3">
        <ScoreBar score={s.score} weak={s.weak} />
      </td>
      <td className="p-3 tabular-nums">{pct(s.on_time_rate_pct)}</td>
      <td className="p-3 tabular-nums">{pct(s.dispute_rate_pct)}</td>
      <td className="p-3 tabular-nums">
        {s.price_index === null ? "—" : formatDecimal(s.price_index, lang, 2)}
      </td>
      <td className="p-3 tabular-nums">{s.your_deals_count}</td>
    </tr>
  );
}
