import Link from "next/link";
import type { ReactNode } from "react";

import { useT } from "@/i18n";
import type { Citation } from "@/lib/api/chat";

const APP_PATH =
  /^\/app(\/[A-Za-z0-9_-]+)*\/?(\?[A-Za-z0-9_\-=&.%]*)?$/;

/** Returns the href only when it is an internal /app route; anything else is rejected. */
export function safeAppHref(href: string | null | undefined): string | null {
  return href && APP_PATH.test(href) ? href : null;
}

const INLINE =
  /(\[S\d+\]|\*\*[^*\n]+\*\*|(?<![\p{L}\p{N}])_[^_\n]+_(?![\p{L}\p{N}])|\[[^\]\n]+\]\([^)\s]+\))/u;

export type CiteCtx = {
  citations: ReadonlyMap<string, Citation>;
  onCite: (id: string) => void;
};

function CiteChip({ cite, onCite }: { cite: Citation; onCite: CiteCtx["onCite"] }) {
  const t = useT();
  return (
    <button
      type="button"
      data-cite={cite.cite_id}
      aria-label={t("chat.cite.label", { id: cite.cite_id, title: cite.title })}
      onClick={() => onCite(cite.cite_id)}
      className="mx-0.5 inline-block rounded-md border border-brand-600 bg-brand-50 px-1 align-baseline text-xs font-bold text-brand-text hover:bg-brand-100 focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
    >
      [{cite.cite_id}]
    </button>
  );
}

function inline(
  text: string,
  keyBase: string,
  depth = 0,
  cites?: CiteCtx,
): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (!part) return null;
    if (/^\[S\d+\]$/.test(part)) {
      const cite = cites?.citations.get(part.slice(1, -1));
      return cite ? (
        <CiteChip key={key} cite={cite} onCite={cites!.onCite} />
      ) : (
        <span key={key}>{part}</span>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      const inner = part.slice(2, -2);
      return (
        <strong key={key}>
          {depth < 1 ? inline(inner, key, depth + 1, cites) : inner}
        </strong>
      );
    }
    if (part.length > 2 && part.startsWith("_") && part.endsWith("_")) {
      const inner = part.slice(1, -1);
      return (
        <em key={key}>{depth < 1 ? inline(inner, key, depth + 1, cites) : inner}</em>
      );
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      const href = safeAppHref(link[2]);
      return href ? (
        <Link
          key={key}
          href={href}
          className="font-semibold text-brand-text underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
        >
          {link[1]}
        </Link>
      ) : (
        <span key={key}>{link[1]}</span>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

const BULLET = /^\s*(?:[-*•])\s+(.*)$/;

/** Minimal, HTML-free markdown: paragraphs, **bold**, _italic_, bullets, line breaks, internal links. */
export function Markdown({
  text,
  className = "",
  cites,
}: {
  text: string;
  className?: string;
  cites?: CiteCtx;
}) {
  const blocks = text.replace(/\r\n?/g, "\n").trim().split(/\n{2,}/);
  return (
    <div className={`space-y-2 break-words ${className}`}>
      {blocks.map((block, bi) => {
        const lines = block.split("\n");
        if (lines.every((l) => BULLET.test(l))) {
          return (
            <ul key={bi} className="list-disc space-y-1 pl-5">
              {lines.map((l, li) => (
                <li key={li}>{inline(BULLET.exec(l)![1], `b${bi}-${li}`, 0, cites)}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={bi}>
            {lines.map((l, li) => (
              <span key={li}>
                {li > 0 ? <br /> : null}
                {inline(l, `p${bi}-${li}`, 0, cites)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
