"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useT } from "@/i18n";
import { DOC_ROLES, type DocFilter, type DocLang, type DocRole, type DocSection } from "@/lib/docs/types";

export type NavItem = { id: string; title: string; roles: DocRole[] };
export type NavSection = { section: DocSection; items: NavItem[] };

const KEY = "setu_docs_filter";

function readFilter(): DocFilter {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "all" || (DOC_ROLES as readonly string[]).includes(v ?? "")) return v as DocFilter;
  } catch {
    /* storage unavailable */
  }
  return "all";
}

type Props = { lang: DocLang; nav: NavSection[]; onNavigate?: () => void };

export function DocsSidebar({ lang, nav, onNavigate }: Props) {
  const t = useT();
  const pathname = usePathname();
  const [filter, setFilter] = useState<DocFilter>("all");
  useEffect(() => {
    const id = setTimeout(() => setFilter(readFilter()), 0);
    return () => clearTimeout(id);
  }, []);

  function choose(f: DocFilter) {
    setFilter(f);
    try {
      localStorage.setItem(KEY, f);
    } catch {
      /* storage unavailable */
    }
  }

  const visible = nav
    .map((s) => ({
      ...s,
      items: s.items.filter((i) => filter === "all" || i.roles.includes(filter) || s.section === "getting-started" || s.section === "glossary"),
    }))
    .filter((s) => s.items.length > 0);

  return (
    <nav aria-label={t("docs.nav.label")} className="space-y-5">
      <div role="group" aria-label={t("docs.filter.label")} className="flex flex-wrap gap-1.5">
        {(["all", ...DOC_ROLES] as DocFilter[]).map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            data-testid={`docs-filter-${f}`}
            onClick={() => choose(f)}
            className={`min-h-9 rounded-full border px-3 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none ${
              filter === f ? "border-brand-700 bg-brand-700 text-white" : "border-line text-ink hover:bg-surface-alt"
            }`}
          >
            {t(`docs.filter.${f}`)}
          </button>
        ))}
      </div>
      {visible.length === 0 ? <p className="text-sm text-muted">{t("docs.empty")}</p> : null}
      {visible.map((s) => (
        <section key={s.section} aria-labelledby={`nav-${s.section}`}>
          <h2 id={`nav-${s.section}`} className="px-2 text-xs font-bold tracking-wide text-muted uppercase">
            {t(`docs.section.${s.section}`)}
          </h2>
          <ul className="mt-1">
            {s.items.map((i) => {
              const href = `/docs/${lang}/${i.id}`;
              const current = pathname === href;
              return (
                <li key={i.id}>
                  <Link
                    href={href}
                    onClick={onNavigate}
                    aria-current={current ? "page" : undefined}
                    className={`flex min-h-10 items-center rounded-lg px-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
                      current ? "bg-surface-alt font-bold text-brand-text" : "text-ink hover:bg-surface-alt"
                    }`}
                  >
                    {i.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </nav>
  );
}
