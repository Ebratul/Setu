"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BackButton } from "@/components/ui/BackButton";
import { Icon } from "@/components/ui/Icon";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { useLang, useT, type Lang } from "@/i18n";
import { DOC_LANGS, type DocLang } from "@/lib/docs/types";

import { DocsSearch } from "./DocsSearch";
import { DocsSidebar, type NavSection } from "./DocsSidebar";

type Props = { lang: DocLang; nav: NavSection[]; langsByPage: Record<string, DocLang[]>; children: ReactNode };

const NAMES: Record<DocLang, string> = { en: "English", bn: "বাংলা", zh: "中文" };

function isEmbed(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("embed") === "1";
  } catch {
    return false;
  }
}

/** Header + sidebar around every docs page. `?embed=1` (help drawer iframe) renders the page alone. */
export function DocsFrame({ lang, nav, langsByPage, children }: Props) {
  const t = useT();
  const { lang: uiLang, setLang } = useLang();
  useEffect(() => {
    if (uiLang !== lang) setLang(lang);
  }, [lang, uiLang, setLang]);
  const pathname = usePathname();
  const [embed, setEmbed] = useState(false);
  const [searching, setSearching] = useState(false);
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setEmbed(isEmbed()), 0);
    return () => clearTimeout(id);
  }, [pathname]);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = (e.target as HTMLElement | null)?.closest("input, textarea, [contenteditable]");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearching((s) => !s);
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        setSearching(true);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const rest = pathname.replace(/^\/docs\/[a-z]{2}\/?/, "");
  const pageId = rest.split("/").slice(0, 2).join("/");
  const available = langsByPage[pageId];

  function hrefFor(l: DocLang) {
    const target = rest && (!available || available.includes(l)) ? rest : "";
    return `/docs/${l}${target ? `/${target}` : ""}`;
  }

  if (embed) {
    return (
      <main id="main" className="docs-print mx-auto w-full max-w-3xl px-4 py-4">
        {children}
      </main>
    );
  }

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:font-semibold focus:text-brand-text focus:ring-2 focus:ring-brand-500"
      >
        {t("landing.skip")}
      </a>
      <header className="no-print sticky top-0 z-40 border-b border-line bg-surface shadow-card">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2">
          <div className="flex items-center gap-2">
            <BackButton fallbackHref="/" />
            <Link
              href={`/docs/${lang}`}
              className="inline-flex min-h-11 items-center gap-2 rounded-md text-lg font-bold text-brand-text focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              Setu সেতু <span className="text-ink">{t("docs.link")}</span>
            </Link>
          </div>
          <div role="group" aria-label={t("topbar.controls")} className="flex flex-wrap items-center gap-2 sm:gap-3">
            <button
              type="button"
              data-testid="docs-search-open"
              aria-haspopup="dialog"
              onClick={() => setSearching(true)}
              className="flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-sm text-muted hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
            >
              <Icon name="search" />
              <span>{t("docs.search.label")}</span>
              <kbd className="hidden rounded border border-line px-1.5 text-xs lg:inline">Ctrl K</kbd>
            </button>
            <nav aria-label={t("lang.label")} className="flex items-center gap-1">
              {DOC_LANGS.map((l) => (
                <Link
                  key={l}
                  href={hrefFor(l)}
                  hrefLang={l}
                  lang={l}
                  aria-current={l === lang ? "page" : undefined}
                  data-testid={`docs-lang-${l}`}
                  className={`inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-semibold focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none ${
                    l === lang ? "bg-brand-700 text-white" : "text-ink hover:bg-surface-alt"
                  }`}
                >
                  {NAMES[l]}
                </Link>
              ))}
            </nav>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-7xl flex-1 gap-8 px-4 py-6">
        <div className="no-print hidden w-64 shrink-0 lg:block">
          <div className="sticky top-24 max-h-[calc(100dvh-7rem)] overflow-y-auto pr-2">
            <DocsSidebar lang={lang} nav={nav} />
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="no-print mb-4 lg:hidden">
            <button
              type="button"
              aria-expanded={menu}
              aria-controls="docs-mobile-nav"
              onClick={() => setMenu((m) => !m)}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-sm font-semibold text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
            >
              <Icon name="menu" />
              {t("docs.nav.menu")}
            </button>
            {menu ? (
              <div id="docs-mobile-nav" className="mt-3 rounded-card border border-line bg-surface p-3">
                <DocsSidebar lang={lang} nav={nav} onNavigate={() => setMenu(false)} />
              </div>
            ) : null}
          </div>
          <main id="main">{children}</main>
        </div>
      </div>
      {searching ? <DocsSearch lang={lang as Lang} onClose={() => setSearching(false)} /> : null}
    </>
  );
}

