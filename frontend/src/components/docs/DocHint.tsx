"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/Icon";
import { useLang, useT } from "@/i18n";

import { useDocForRoute } from "./HelpButton";

const key = (user: string, id: string) => `setu_doc_hint:${user}:${id}`;

/** One-time, dismissible "new here?" banner linking to the guide for this screen (remembered per user in this browser). */
export function DocHint({ userId }: { userId?: string }) {
  const t = useT();
  const { lang } = useLang();
  const pathname = usePathname();
  const hit = useDocForRoute(pathname);
  const [seen, setSeen] = useState(true);
  const id = hit?.id;
  useEffect(() => {
    if (!id || !userId) return;
    const timer = setTimeout(() => {
      try {
        setSeen(localStorage.getItem(key(userId, id)) === "1");
      } catch {
        setSeen(true);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [id, userId]);

  if (!id || !userId || seen) return null;

  function dismiss() {
    try {
      localStorage.setItem(key(userId as string, id as string), "1");
    } catch {
      /* storage unavailable */
    }
    setSeen(true);
  }

  return (
    <aside
      data-testid="doc-hint"
      className="no-print mb-4 flex items-start gap-3 rounded-card border border-info bg-info-soft p-3 text-sm text-ink"
    >
      <Icon name="info" size={18} className="mt-0.5 shrink-0" />
      <p className="min-w-0 flex-1">
        <strong>{t("docs.hint.title")}</strong> {t("docs.hint.body")}{" "}
        <Link href={`/docs/${lang}/${id}`} onClick={dismiss} className="font-semibold text-brand-text underline">
          {t("docs.hint.read")}
        </Link>
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label={t("docs.hint.dismiss")}
        className="flex size-9 shrink-0 items-center justify-center rounded-lg hover:bg-surface focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
      >
        <Icon name="x" size={16} />
      </button>
    </aside>
  );
}
