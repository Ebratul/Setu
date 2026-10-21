"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useT, type Lang } from "@/i18n";
import { loadIndex, snippet, type DocHit, type DocIndex } from "@/lib/docs/search";
import { useDialog } from "@/lib/useDialog";

type Props = { lang: Lang; onClose: () => void };

export function DocsSearch({ lang, onClose }: Props) {
  const t = useT();
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [index, setIndex] = useState<DocIndex | null>(null);
  const [failed, setFailed] = useState(false);
  useDialog(panel, onClose);
  useEffect(() => input.current?.focus(), []);
  useEffect(() => {
    let alive = true;
    loadIndex(lang).then(
      (i) => alive && setIndex(i),
      () => alive && setFailed(true),
    );
    return () => {
      alive = false;
    };
  }, [lang]);

  const hits = useMemo<DocHit[]>(() => (index ? index.search(query, 12) : []), [index, query]);

  function go(h: DocHit) {
    onClose();
    router.push(h.url);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && hits[active]) {
      e.preventDefault();
      go(hits[active]);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-scrim p-4 pt-[10vh]" onClick={onClose}>
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={t("docs.search.label")}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-card bg-surface shadow-pop focus:outline-none"
      >
        <div className="flex items-center gap-2 border-b border-line px-4">
          <Icon name="search" className="text-muted" />
          <input
            ref={input}
            type="search"
            role="combobox"
            aria-expanded={hits.length > 0}
            aria-controls={listId}
            aria-activedescendant={hits[active] ? `${listId}-${active}` : undefined}
            aria-label={t("docs.search.label")}
            placeholder={t("docs.search.placeholder")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKey}
            className="min-h-12 w-full bg-transparent text-ink outline-none placeholder:text-muted"
          />
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          <ul id={listId} role="listbox" aria-label={t("docs.search.label")}>
            {hits.map((h, i) => (
              <li
                key={h.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(h)}
                className={`cursor-pointer border-b border-line px-4 py-3 last:border-0 ${i === active ? "bg-surface-alt" : ""}`}
              >
                <p className="text-xs font-semibold text-brand-text">{t(`docs.section.${h.section}`)}</p>
                <p className="font-semibold text-ink">{h.title}</p>
                <p className="line-clamp-2 text-sm text-muted">{snippet(h.text || h.summary, query)}</p>
              </li>
            ))}
          </ul>
          <p role="status" className="px-4 py-3 text-sm text-muted">
            {failed
              ? t("docs.missing")
              : !query.trim()
                ? t("docs.search.hint")
                : index && hits.length === 0
                  ? t("docs.search.empty", { q: query })
                  : hits.length
                    ? t("docs.search.results", { n: hits.length })
                    : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
