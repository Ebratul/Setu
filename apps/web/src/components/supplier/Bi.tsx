"use client";

import { messages, translate, useLang, useT } from "@/i18n";

type Props = { k: string; vars?: Record<string, string | number> };

/** English text with the Chinese label alongside (the supplier portal's bilingual headings). */
export function Bi({ k, vars }: Props) {
  const t = useT();
  const { lang } = useLang();
  const zh = messages.zh[k];
  return (
    <>
      {t(k, vars)}
      {lang === "en" && zh ? (
        <span lang="zh" className="ml-2 text-[0.8em] font-medium text-muted">
          {translate("zh", k, vars)}
        </span>
      ) : null}
    </>
  );
}
