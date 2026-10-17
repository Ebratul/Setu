"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { hasKey, pickLang, useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatDate, formatMoney, formatPct, type Currency } from "@/lib/format";

import { safeAppHref } from "../markdown";

const APPLY_ROUTE = /^\/app\/financing\/?(\?[A-Za-z0-9_\-=&.%]*)?$/;
import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "financing_comparison" }>;

export function FinancingComparisonCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const cur = d.currency as Currency;
  const money = (v: string) => formatMoney(v, cur, lang);
  const applyHref = APPLY_ROUTE.test(d.apply_route) ? safeAppHref(d.apply_route) : null;
  const options = [...d.options].sort((a, b) => a.rank - b.rank);
  const reasons = (d.recommended?.reasons ?? []).filter(
    (r) => r.code !== "PICK",
  );
  return (
    <CardShell
      type="financing_comparison"
      title={t("chat.card.financing")}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
    >
      {d.no_financing_needed ? (
        <p className="text-sm font-semibold text-success">
          {t("fin.noneNeeded")}
        </p>
      ) : (
        <p className="text-xs text-muted">
          {t("chat.fin.need", {
            amount: money(d.amount),
            date: formatDate(d.needed_by, lang),
            days: d.needed_for_days,
          })}
        </p>
      )}
      <ol className="space-y-2">
        {options.map((o) => {
          const kindKey = `fin.kind.${o.kind}`;
          const style = o.recommended
            ? "border-2 border-brand-600 bg-brand-50"
            : o.eligible
              ? "border border-line bg-surface"
              : "border border-dashed border-muted bg-surface-alt text-muted";
          return (
            <li
              key={o.option_id}
              data-testid="chat-option"
              data-code={o.code}
              data-recommended={o.recommended}
              data-eligible={o.eligible}
              className={`space-y-2 rounded-xl p-3 ${style}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{`#${o.rank}`}</Badge>
                {o.recommended ? (
                  <Badge tone="success" icon="★">
                    {t("fin.recommended")}
                  </Badge>
                ) : null}
                {!o.eligible ? (
                  <Badge tone="danger" icon="✕">
                    {t("fin.ineligible")}
                  </Badge>
                ) : null}
              </div>
              <p className="text-sm font-bold break-words text-ink">{o.name}</p>
              <p className="text-xs text-muted">
                {hasKey(kindKey) ? t(kindKey) : o.kind}
              </p>
              <dl className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <dt className="text-muted">{t("fin.opt.total")}</dt>
                  <dd className="font-bold text-ink">{money(o.total_cost)}</dd>
                </div>
                <div>
                  <dt className="text-muted">{t("fin.opt.ear")}</dt>
                  <dd className="font-bold text-ink">
                    {formatPct(o.effective_annual_rate_pct, lang)}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">{t("fin.opt.tenor")}</dt>
                  <dd className="font-bold text-ink">
                    {t("fin.days", { n: o.tenor_days })}
                  </dd>
                </div>
              </dl>
              {o.recommended && reasons.length > 0 ? (
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink">
                  {reasons.map((r) => (
                    <li key={r.code}>{pickLang(r, lang)}</li>
                  ))}
                </ul>
              ) : null}
              {!o.eligible && o.why_not.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold text-danger">
                    {t("fin.whyNot")}
                  </p>
                  <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink">
                    {o.why_not.map((w) => (
                      <li key={w.code}>{pickLang(w, lang)}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {o.recommended && applyHref ? (
                <Link
                  href={applyHref}
                  className="inline-block rounded-xl bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  {t("fin.apply.button")}
                </Link>
              ) : null}
            </li>
          );
        })}
      </ol>
    </CardShell>
  );
}
