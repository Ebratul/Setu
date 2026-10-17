"use client";

import { useLang, pickLang } from "@/i18n";

type Props = { items: { code: string; en: string; bn: string }[] };

export function ExplanationList({ items }: Props) {
  const { lang } = useLang();
  if (items.length === 0) return null;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-ink">
      {items.map((x) => (
        <li key={x.code}>{pickLang(x, lang)}</li>
      ))}
    </ul>
  );
}
