import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { DocsFrame } from "@/components/docs/DocsFrame";
import { buildNav, langsByPage } from "@/lib/docs/nav";
import { DOC_LANGS, isDocLang } from "@/lib/docs/types";

export function generateStaticParams() {
  return DOC_LANGS.map((lang) => ({ lang }));
}

export default async function DocsLangLayout({ children, params }: { children: ReactNode; params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isDocLang(lang)) notFound();
  return (
    <DocsFrame lang={lang} nav={buildNav(lang)} langsByPage={langsByPage()}>
      {children}
    </DocsFrame>
  );
}
