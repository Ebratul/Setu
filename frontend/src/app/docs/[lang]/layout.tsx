import { notFound } from "next/navigation";
import { Suspense, type ReactNode } from "react";

import { DocsFrame } from "@/components/docs/DocsFrame";
import { buildNav, langsByPage } from "@/lib/docs/nav";
import { DOC_LANGS, isDocLang } from "@/lib/docs/types";

export function generateStaticParams() {
  return DOC_LANGS.map((lang) => ({ lang }));
}

type LayoutProps = { children: ReactNode; params: Promise<{ lang: string }> };

export default function DocsLangLayout(props: LayoutProps) {
  return (
    <Suspense fallback={null}>
      <DocsLangContent {...props} />
    </Suspense>
  );
}

async function DocsLangContent({ children, params }: LayoutProps) {
  const { lang } = await params;
  if (!isDocLang(lang)) notFound();
  return (
    <DocsFrame lang={lang} nav={buildNav(lang)} langsByPage={langsByPage()}>
      {children}
    </DocsFrame>
  );
}
