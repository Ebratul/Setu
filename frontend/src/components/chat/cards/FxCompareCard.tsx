"use client";

import { Badge } from "@/components/ui/Badge";
import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatDate, formatMoney, formatPct, type Currency } from "@/lib/format";

import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "fx_compare" }>;
type Route = Card["data"]["usd_route"];

export function FxCompareCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const payer = d.payer_currency as Currency;
  const money = (v: string, c: Currency = payer) => formatMoney(v, c, lang);
  const routes: Route[] = [d.usd_route, d.cny_route];
  return (
    <CardShell
      type="fx_compare"
      title={t("chat.card.fx")}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
    >
      <p className="text-xs text-muted">
        {t("chat.fx.invoice", {
          amount: money(d.invoice_amount, d.invoice_currency),
          basis: d.basis,
        })}
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {routes.map((r) => {
          const cheaper = d.cheaper === r.route;
          return (
            <section
              key={r.route}
              data-route={r.route}
              data-cheaper={cheaper}
              aria-label={t("chat.fx.route", { cur: r.route })}
              className={`min-w-0 space-y-1 rounded-xl p-3 text-xs ${
                cheaper
                  ? "border-2 border-brand-600 bg-brand-50"
                  : "border border-line bg-surface"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-sm font-bold text-ink">
                  {t("chat.fx.route", { cur: r.route })}
                </h4>
                {cheaper ? (
                  <Badge tone="success" icon="★">
                    {t("chat.fx.cheaper")}
                  </Badge>
                ) : null}
              </div>
              <dl className="space-y-0.5">
                <Row k={t("chat.fx.sent")} v={money(r.sent, r.sent_currency)} />
                <Row k={t("chat.fx.rate")} v={r.rate_used} />
                <Row k={t("chat.fx.conversion")} v={money(r.conversion)} />
                <Row k={t("chat.fx.fees")} v={money(r.fees)} />
                <Row k={t("fin.opt.total")} v={money(r.total)} strong />
              </dl>
            </section>
          );
        })}
      </div>
      <p className="text-sm font-semibold text-success">
        {t("chat.fx.saving", {
          cur: d.cheaper,
          amount: money(d.saving),
          pct: formatPct(d.saving_pct, lang),
        })}
      </p>
      <p className="text-xs font-semibold text-warning">
        {t("chat.fx.mock", { date: formatDate(d.as_of, lang) })}
      </p>
      <details className="text-xs text-ink">
        <summary className="cursor-pointer rounded-md font-semibold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none">
          {t("chat.fx.assumptions")}
        </summary>
        <ul className="mt-1 list-disc space-y-0.5 pl-5">
          {d.assumptions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      </details>
    </CardShell>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-muted">{k}</dt>
      <dd className={`text-right break-words ${strong ? "font-bold" : ""} text-ink`}>
        {v}
      </dd>
    </div>
  );
}
