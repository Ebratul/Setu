"use client";

import { useEffect, useState } from "react";

import { useT } from "@/i18n";
import type { TocItem } from "@/lib/docs/types";

export function DocsToc({ items }: { items: TocItem[] }) {
  const t = useT();
  const [active, setActive] = useState<string>("");
  useEffect(() => {
    const els = items.map((i) => document.getElementById(i.id)).filter((e): e is HTMLElement => !!e);
    if (els.length === 0) return;
    const obs = new IntersectionObserver(
      (entries) => {
        const first = entries.find((e) => e.isIntersecting);
        if (first) setActive(first.target.id);
      },
      { rootMargin: "-80px 0px -70% 0px" },
    );
    els.forEach((e) => obs.observe(e));
    return () => obs.disconnect();
  }, [items]);
  if (items.length === 0) return null;
  return (
    <nav aria-label={t("docs.onThisPage")} className="no-print text-sm">
      <p className="mb-2 font-bold text-ink">{t("docs.onThisPage")}</p>
      <ul className="space-y-1 border-l border-line">
        {items.map((i) => (
          <li key={i.id}>
            <a
              href={`#${i.id}`}
              aria-current={active === i.id ? "location" : undefined}
              className={`-ml-px block border-l-2 py-1 pr-2 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
                i.depth === 3 ? "pl-6" : "pl-3"
              } ${active === i.id ? "border-brand-text font-semibold text-brand-text" : "border-transparent text-muted hover:text-ink"}`}
            >
              {i.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
