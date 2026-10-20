"use client";

import Link from "next/link";

import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import type { ScoreItem } from "@/lib/api/demo";

import { biText, toDemoLang } from "./demoModel";

const GROUPS = ["TASK", "SECURITY", "INNOVATION"] as const;

/** Judge scorecard: items tick live; each links to the screen that proves it (opens outside the demo frame). */
export function Scorecard({ items }: { items: ScoreItem[] }) {
  const t = useT();
  const lang = toDemoLang(useLang().lang);
  const ticked = items.filter((i) => i.ticked).length;
  return (
    <section aria-labelledby="demo-score-h" data-testid="scorecard" className="space-y-3">
      <h2 id="demo-score-h" className="flex items-baseline justify-between gap-2 text-lg font-bold text-ink">
        {t("demo.score.title")}
        <span aria-live="polite" className="text-sm font-semibold text-muted" data-testid="score-count">
          {t("demo.score.count", { done: ticked, total: items.length })}
        </span>
      </h2>
      {GROUPS.map((g) => {
        const list = items.filter((i) => i.group === g);
        if (list.length === 0) return null;
        return (
          <div key={g}>
            <h3 className="text-sm font-bold text-muted">{t(`demo.group.${g}`)}</h3>
            <ul className="mt-1 space-y-1">
              {list.map((i) => (
                <li key={i.id} data-ticked={i.ticked} className="flex items-start gap-2 text-sm">
                  <span
                    className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border ${
                      i.ticked ? "border-success bg-success-soft text-success" : "border-line bg-surface text-muted"
                    }`}
                  >
                    <Icon name={i.ticked ? "check" : "circle"} size={12} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="sr-only">{i.ticked ? t("demo.score.done") : t("demo.score.todo")}: </span>
                    <Link
                      href={i.link}
                      target="_blank"
                      rel="noopener"
                      className="rounded font-semibold text-ink hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                    >
                      {biText(i.label, lang)}
                      <span className="sr-only"> ({t("demo.score.opens")})</span>
                    </Link>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
