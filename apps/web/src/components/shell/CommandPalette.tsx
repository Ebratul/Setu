"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Icon, type IconName } from "@/components/ui/Icon";
import { useT } from "@/i18n";
import { getMe } from "@/lib/api/auth";
import { listDeals } from "@/lib/api/deals";
import { getSuppliers } from "@/lib/api/kyb";
import { openChat } from "@/lib/shortcuts";
import { useApi } from "@/lib/useApi";
import { useDialog } from "@/lib/useDialog";

import { fuzzyScore } from "./fuzzy";
import { navGroups } from "./navItems";

type Entry = {
  id: string;
  group: "cmd.groupActions" | "cmd.groupPages" | "cmd.groupDeals" | "cmd.groupSuppliers";
  label: string;
  hint?: string;
  icon: IconName;
  run: () => void;
};

type Props = { onClose: () => void };

const MAX_RESULTS = 24;

/** Ctrl/Cmd+K palette: an ARIA combobox over pages, deals, suppliers and quick actions. */
export default function CommandPalette({ onClose }: Props) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const baseId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useDialog(panel, onClose);
  useEffect(() => input.current?.focus(), []);

  const me = useApi((s) => getMe(s), "me");
  // Deals and suppliers load lazily on open; failures just leave those groups empty.
  const deals = useApi((s) => listDeals(undefined, s), "palette-deals");
  const suppliers = useApi((s) => getSuppliers(s), "palette-suppliers");

  const entries = useMemo<Entry[]>(() => {
    const go = (href: string) => () => {
      onClose();
      router.push(href);
    };
    const list: Entry[] = [
      { id: "a-new", group: "cmd.groupActions", label: t("cmd.newOrder"), icon: "plus", run: go("/app/deals/new") },
      { id: "a-doc", group: "cmd.groupActions", label: t("cmd.checkDoc"), icon: "file", run: go("/app/deals") },
      {
        id: "a-chat",
        group: "cmd.groupActions",
        label: t("cmd.askSetu"),
        icon: "chat",
        run: () => {
          onClose();
          if (pathname.startsWith("/app/chat")) router.push("/app/chat");
          else setTimeout(openChat, 50);
        },
      },
    ];
    const seen = new Set<string>();
    for (const g of navGroups(me.data?.role)) {
      for (const item of g.items) {
        const key = `${item.href}|${item.key}`;
        if (seen.has(key)) continue;
        seen.add(key);
        list.push({ id: `p-${key}`, group: "cmd.groupPages", label: t(item.key), icon: item.icon, run: go(item.href) });
      }
    }
    for (const d of deals.data?.deals ?? []) {
      list.push({
        id: `d-${d.id}`,
        group: "cmd.groupDeals",
        label: `${d.reference} · ${d.title}`,
        hint: d.supplier_name,
        icon: "box",
        run: go(`/app/deals/${encodeURIComponent(d.reference)}`),
      });
    }
    for (const s of suppliers.data?.suppliers ?? []) {
      list.push({
        id: `s-${s.supplier_id}`,
        group: "cmd.groupSuppliers",
        label: s.name,
        hint: s.city,
        icon: "users",
        run: go(`/app/suppliers/${s.supplier_id}`),
      });
    }
    return list;
  }, [t, me.data?.role, deals.data, suppliers.data, router, onClose, pathname]);

  const results = useMemo(() => {
    const scored: { e: Entry; score: number }[] = [];
    for (const e of entries) {
      const score = fuzzyScore(query, `${e.label} ${e.hint ?? ""}`);
      if (score !== null) scored.push({ e, score });
    }
    if (query.trim()) scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, MAX_RESULTS).map((x) => x.e);
  }, [entries, query]);

  const current = results.length ? Math.min(active, results.length - 1) : -1;
  const optId = (i: number) => `${baseId}-opt-${i}`;

  function move(next: number) {
    setActive(next);
    requestAnimationFrame(() => document.getElementById(optId(next))?.scrollIntoView?.({ block: "nearest" }));
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      move((current + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move((current - 1 + results.length) % results.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      move(0);
    } else if (e.key === "End") {
      e.preventDefault();
      move(results.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      results[current]?.run();
    }
  }

  const titleId = `${baseId}-title`;
  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-scrim p-3 pt-[10dvh] sm:p-6 sm:pt-[12dvh]" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="command-palette"
        onClick={(e) => e.stopPropagation()}
        className="anim-pop flex max-h-[76dvh] w-full max-w-xl flex-col overflow-hidden rounded-card bg-surface shadow-pop focus:outline-none"
      >
        <h2 id={titleId} className="sr-only">
          {t("cmd.title")}
        </h2>
        <div className="flex items-center gap-2 border-b border-line px-4">
          <Icon name="search" className="shrink-0 text-muted" />
          <input
            role="combobox"
            aria-label={t("cmd.label")}
            aria-expanded="true"
            aria-controls={`${baseId}-list`}
            aria-activedescendant={current >= 0 ? optId(current) : undefined}
            aria-autocomplete="list"
            autoComplete="off"
            ref={input}
            value={query}
            placeholder={t("cmd.placeholder")}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKeyDown}
            className="min-h-14 w-full bg-transparent py-3 text-base text-ink placeholder:text-muted focus:outline-none"
          />
        </div>
        <ul id={`${baseId}-list`} role="listbox" aria-label={t("cmd.title")} className="min-h-0 flex-1 overflow-y-auto p-2">
          {results.map((e, i) => {
            const header = e.group !== lastGroup;
            lastGroup = e.group;
            return (
              <li key={e.id} role="presentation">
                {header ? (
                  <p role="presentation" className="px-3 pt-2 pb-1 text-xs font-bold tracking-wide text-muted uppercase">
                    {t(e.group)}
                  </p>
                ) : null}
                <div
                  id={optId(i)}
                  role="option"
                  aria-selected={i === current}
                  onMouseMove={() => i !== current && setActive(i)}
                  onClick={() => e.run()}
                  className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm ${
                    i === current ? "bg-brand-700 text-white" : "text-ink"
                  }`}
                >
                  <Icon name={e.icon} className="shrink-0" />
                  <span className="min-w-0 flex-1 break-words font-semibold">{e.label}</span>
                  {e.hint ? (
                    <span className={`shrink-0 text-xs ${i === current ? "text-white" : "text-muted"}`}>{e.hint}</span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
        <p aria-live="polite" role="status" className="sr-only">
          {results.length ? t("cmd.results", { n: results.length }) : t("cmd.empty", { q: query })}
        </p>
        {results.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted">{t("cmd.empty", { q: query })}</p>
        ) : null}
        <p className="hidden border-t border-line px-4 py-2 text-xs text-muted sm:block">{t("cmd.hint")}</p>
      </div>
    </div>
  );
}
