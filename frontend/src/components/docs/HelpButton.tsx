"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Drawer } from "@/components/ui/Drawer";
import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";
import { pickDocForRoute, type RouteMapEntry } from "@/lib/docs/types";

let routesPromise: Promise<RouteMapEntry[]> | null = null;

export function loadRouteMap(): Promise<RouteMapEntry[]> {
  routesPromise ??= fetch("/docs-data/routes")
    .then((r) => (r.ok ? (r.json() as Promise<RouteMapEntry[]>) : []))
    .catch(() => {
      routesPromise = null;
      return [];
    });
  return routesPromise;
}

/** The doc page that explains the screen at `pathname`, if one is mapped. */
export function useDocForRoute(pathname: string): RouteMapEntry | undefined | null {
  const [entries, setEntries] = useState<RouteMapEntry[] | null>(null);
  useEffect(() => {
    let alive = true;
    loadRouteMap().then((e) => alive && setEntries(e));
    return () => {
      alive = false;
    };
  }, []);
  if (entries === null) return null;
  return pickDocForRoute(entries, pathname);
}

/** "?" button in the top bar: opens the guide for the current screen in a side drawer. */
export function HelpButton() {
  const t = useT();
  const { lang } = useLang();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const hit = useDocForRoute(pathname);
  return (
    <>
      <button
        type="button"
        data-testid="help-button"
        aria-haspopup="dialog"
        aria-label={t("docs.help.button")}
        title={t("docs.help.button")}
        onClick={() => setOpen(true)}
        className="flex size-11 items-center justify-center rounded-xl border border-line text-lg font-bold text-ink hover:bg-surface-alt focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none"
      >
        <span aria-hidden="true">?</span>
      </button>
      {open ? (
        <Drawer title={t("docs.help.title")} onClose={() => setOpen(false)}>
          {hit ? (
            <div className="space-y-3">
              <iframe
                title={t("docs.help.title")}
                data-testid="help-frame"
                src={`/docs/${lang}/${hit.id}?embed=1`}
                className="h-[60dvh] w-full rounded-card border border-line bg-surface"
              />
              <Link
                href={`/docs/${lang}/${hit.id}`}
                data-testid="help-open-guide"
                className="inline-flex min-h-11 items-center gap-1 font-semibold text-brand-text underline"
              >
                {t("docs.help.open")} <Icon name="external" size={14} />
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-ink">{t("docs.help.none")}</p>
              <Link href={`/docs/${lang}`} className="inline-flex min-h-11 items-center font-semibold text-brand-text underline">
                {t("docs.help.browse")}
              </Link>
            </div>
          )}
        </Drawer>
      ) : null}
    </>
  );
}
