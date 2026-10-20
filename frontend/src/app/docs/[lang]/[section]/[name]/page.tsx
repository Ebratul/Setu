import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/docs/Breadcrumbs";
import { DocBody } from "@/components/docs/DocArticle";
import { DocMetaBar } from "@/components/docs/DocMetaBar";
import { DocsToc } from "@/components/docs/DocsToc";
import { PageFeedback } from "@/components/docs/PageFeedback";
import { PrevNext } from "@/components/docs/PrevNext";
import { RoleBadge } from "@/components/docs/mdx/RoleBadge";
import { getDocWithFallback, listDocs } from "@/lib/docs/content";
import { compileMdx } from "@/lib/docs/mdx";
import { readingOrder } from "@/lib/docs/nav";
import { DOC_LANGS, GUIDE_SECTIONS, isDocLang } from "@/lib/docs/types";

type Params = { lang: string; section: string; name: string };

export function generateStaticParams() {
  return DOC_LANGS.flatMap((lang) =>
    listDocs(lang).map((d) => {
      const [section, name] = d.meta.id.split("/");
      return { lang, section, name };
    }),
  );
}

export async function generateMetadata({ params }: { params: Promise<Params> }): Promise<Metadata> {
  const { lang, section, name } = await params;
  if (!isDocLang(lang)) return {};
  const hit = getDocWithFallback(lang, `${section}/${name}`);
  if (!hit) return {};
  return {
    title: hit.doc.meta.title,
    description: hit.doc.meta.summary,
    alternates: { canonical: `/docs/${lang}/${section}/${name}` },
  };
}

export default async function DocPage({ params }: { params: Promise<Params> }) {
  const { lang, section, name } = await params;
  if (!isDocLang(lang)) notFound();
  const id = `${section}/${name}`;
  const hit = getDocWithFallback(lang, id);
  if (!hit) notFound();
  const { doc, fellBack } = hit;
  const { toc } = await compileMdx(doc.body);

  const order = readingOrder(lang);
  const at = order.findIndex((m) => m.id === id);
  const link = (i: number) => (order[i] ? { href: `/docs/${lang}/${order[i].id}`, title: order[i].title } : undefined);

  return (
    <div className="flex gap-8">
      <article className="docs-print min-w-0 flex-1">
        <Breadcrumbs lang={lang} section={doc.meta.section} title={doc.meta.title} />
        <h1 className="text-3xl font-bold text-ink">{doc.meta.title}</h1>
        <p className="mt-2 text-lg text-muted">{doc.meta.summary}</p>
        <DocMetaBar
          lang={lang}
          fellBack={fellBack}
          updated={doc.meta.updated}
          guide={GUIDE_SECTIONS.includes(doc.meta.section) ? doc.meta.section : undefined}
          roles={doc.meta.roles.map((r) => <RoleBadge key={r} role={r} />)}
        />
        <div className="mt-6">
          <DocBody doc={doc} lang={lang} />
        </div>
        <PrevNext prev={link(at - 1)} next={link(at + 1)} />
        <PageFeedback pageId={`${lang}:${id}`} />
        <p className="no-print mt-6">
          <Link href={`/docs/${lang}`} className="font-semibold text-brand-text underline">
            {"←"} Documentation
          </Link>
        </p>
      </article>
      <aside className="no-print hidden w-56 shrink-0 xl:block">
        <div className="sticky top-24">
          <DocsToc items={toc} />
        </div>
      </aside>
    </div>
  );
}

