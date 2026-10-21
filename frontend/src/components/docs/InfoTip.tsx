"use client";

import Link from "next/link";
import { useId, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";

type Props = {
  /** One of docs.tip.<topic>. */
  topic: "tier" | "fraud" | "cooling" | "kyb";
  /** Doc page id, optionally with `#anchor`. */
  doc: string;
};

/** Small (i) button: a one-line explanation plus a link to the matching guide anchor. */
export function InfoTip({ topic, doc }: Props) {
  const t = useT();
  const { lang } = useLang();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [page, anchor] = doc.split("#");
  return (
    <span className="relative inline-flex" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={t("docs.tip.label")}
        data-testid={`info-tip-${topic}`}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex size-6 items-center justify-center rounded-full text-muted hover:text-ink focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        <Icon name="info" size={16} />
      </button>
      {open ? (
        <span
          id={id}
          role="note"
          className="absolute top-7 left-0 z-30 w-64 rounded-xl border border-line bg-surface p-3 text-left text-sm font-normal text-ink shadow-pop"
        >
          {t(`docs.tip.${topic}`)}{" "}
          <Link href={`/docs/${lang}/${page}${anchor ? `#${anchor}` : ""}`} className="font-semibold text-brand-text underline">
            {t("docs.tip.more")}
          </Link>
        </span>
      ) : null}
    </span>
  );
}
