"use client";

import { Money } from "@/components/analysis/Money";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useLang, useT, hasKey, pickLang } from "@/i18n";
import type { Currency } from "@/lib/api/analysis";
import type { OptionQuote, TopPick } from "@/lib/api/financing";
import { formatDate, formatMoney, formatPct } from "@/lib/format";

type Props = {
  option: OptionQuote;
  pick: TopPick | null;
  currency: Currency;
  onSchedule: (o: OptionQuote) => void;
  onImpact: (o: OptionQuote) => void;
  onApply: (o: OptionQuote) => void;
};

export function OptionCard({
  option: o,
  pick,
  currency,
  onSchedule,
  onImpact,
  onApply,
}: Props) {
  const t = useT();
  const { lang } = useLang();
  const headId = `opt-${o.code}-h`;
  const kindKey = `fin.kind.${o.kind}`;
  const block = o.registry_block ?? null;
  const recommended = o.recommended && !block;
  const whyNot = block ? o.why_not.filter((c) => c.code !== block.code) : o.why_not;
  const saving = recommended ? pick?.saving_vs_next : null;
  const rows: [string, React.ReactNode][] = [
    [
      t("fin.opt.interest"),
      <Money key="i" amounts={o.cost.interest} currency={currency} />,
    ],
    [
      t("fin.opt.fees"),
      <Money key="f" amounts={o.cost.fees} currency={currency} />,
    ],
    [
      t("fin.opt.uplift"),
      <Money key="u" amounts={o.cost.uplift} currency={currency} />,
    ],
    [
      t("fin.opt.flat"),
      <Money key="fl" amounts={o.cost.flat} currency={currency} />,
    ],
    [t("fin.opt.tenor"), t("fin.days", { n: o.tenor_days })],
    [t("fin.opt.maturity"), formatDate(o.maturity_on, lang)],
    [t("fin.opt.ear"), formatPct(o.cost.effective_annual_rate_pct, lang)],
    [
      t("fin.opt.per30"),
      <Money key="p" amounts={o.cost.per_30_days} currency={currency} />,
    ],
  ];
  const style = recommended
    ? "border-2 border-brand-600 bg-brand-50 shadow-card-hover"
    : o.eligible
      ? "border border-line bg-surface shadow-card"
      : "border border-dashed border-muted bg-surface-alt";
  return (
    <li
      data-testid="option-card"
      data-code={o.code}
      data-recommended={recommended}
      data-blocked={block ? "true" : undefined}
      data-eligible={o.eligible}
    >
      <article
        aria-labelledby={headId}
        className={`flex h-full flex-col gap-4 rounded-card p-5 ${style}`}
      >
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {recommended ? (
              <Badge tone="success" icon="★">
                {t("fin.recommended")}
              </Badge>
            ) : null}
            {o.eligible ? (
              <Badge tone="success" icon="✓">
                {t("fin.eligible")}
              </Badge>
            ) : (
              <Badge tone="danger" icon="✕">
                {t("fin.ineligible")}
              </Badge>
            )}
            {block ? (
              <Badge tone="danger" icon="■">
                {t("fin.registryBlocked")}
              </Badge>
            ) : null}
            <Badge>{`#${o.rank}`}</Badge>
          </div>
          <h3 id={headId} className="text-lg font-bold text-ink">
            {o.name}
          </h3>
          <p className="text-sm text-muted">
            {o.provider_name ? `${o.provider_name} · ` : ""}
            {hasKey(kindKey) ? t(kindKey) : o.kind}
          </p>
        </header>

        <div>
          <p className="text-sm text-muted">{t("fin.opt.total")}</p>
          <p className="text-2xl font-bold text-ink">
            <Money amounts={o.cost.total} currency={currency} />
          </p>
          {saving ? (
            <p className="text-sm font-semibold text-success">
              {t("fin.saves", {
                amount: formatMoney(saving[currency], currency, lang),
              })}
            </p>
          ) : null}
        </div>

        {recommended && pick && pick.sentences.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
            {pick.sentences.map((s) => (
              <li key={s.code}>{pickLang(s, lang)}</li>
            ))}
          </ul>
        ) : null}

        {block ? (
          <p
            data-testid="registry-block"
            className="rounded-xl border-2 border-danger bg-danger-soft p-3 text-sm font-semibold text-danger"
          >
            <span aria-hidden="true">■ </span>
            {lang === "bn" ? block.reason_bn : block.reason_en}
          </p>
        ) : null}

        {!o.eligible && whyNot.length > 0 ? (
          <div className="rounded-xl border border-danger bg-danger-soft p-3">
            <h4 className="text-sm font-semibold text-danger">
              {t("fin.whyNot")}
            </h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink">
              {whyNot.map((c) => (
                <li key={c.code}>{pickLang(c, lang)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k}>
              <dt className="text-muted">{k}</dt>
              <dd className="font-semibold text-ink">{v}</dd>
            </div>
          ))}
        </dl>

        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-muted">{t("fin.opt.collateral")}</dt>
            <dd className="text-ink">{o.collateral}</dd>
          </div>
          <div>
            <dt className="text-muted">
              {t("fin.opt.conditions", { n: o.condition_count })}
            </dt>
            <dd className="text-ink">{o.conditions}</dd>
          </div>
        </dl>

        {o.risk_notes.length > 0 ? (
          <div>
            <h4 className="text-sm font-semibold text-ink">
              {t("fin.opt.risks")}
            </h4>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted">
              {o.risk_notes.map((r) => (
                <li key={r.code}>{pickLang(r, lang)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {o.eligible && !block ? (
          <div className="mt-auto flex flex-wrap gap-2 pt-2">
            <Button variant="primary" onClick={() => onApply(o)}>
              {t("fin.apply.button")}
            </Button>
            <Button variant="secondary" onClick={() => onImpact(o)}>
              {t("fin.impact.button")}
            </Button>
            <Button variant="secondary" onClick={() => onSchedule(o)}>
              {t("fin.schedule.button")}
            </Button>
          </div>
        ) : null}
      </article>
    </li>
  );
}
