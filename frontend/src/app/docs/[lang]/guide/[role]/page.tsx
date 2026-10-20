import type { Metadata } from "next";
import { Suspense } from "react";
import { notFound } from "next/navigation";

import { DocBody } from "@/components/docs/DocArticle";
import { PrintBar } from "@/components/docs/PrintBar";
import { guideDocs } from "@/lib/docs/content";
import { DOC_LANGS, GUIDE_SECTIONS, isDocLang } from "@/lib/docs/types";

type Params = { lang: string; role: string };

export function generateStaticParams() {
  return DOC_LANGS.flatMap((lang) =>
    GUIDE_SECTIONS.map((role) => ({ lang, role })),
  );
}

export const metadata: Metadata = { title: "Guide", robots: { index: false } };

/** One document with every page of a role guide, for "Save as PDF" / printing. */
export default function GuidePrintPage({
  params,
}: {
  params: Promise<Params>;
}) {
  return (
    <Suspense fallback={null}>
      <GuidePrintPageContent params={params} />
    </Suspense>
  );
}

async function GuidePrintPageContent({ params }: { params: Promise<Params> }) {
  const { lang, role } = await params;
  if (!isDocLang(lang) || !(GUIDE_SECTIONS as readonly string[]).includes(role))
    notFound();
  const docs = guideDocs(lang, role as (typeof GUIDE_SECTIONS)[number]);
  if (docs.length === 0) notFound();
  return (
    <div>
      <PrintBar role={role} lang={lang} />
      <div className="docs-print">
        {docs.map((d, i) => (
          <section
            key={d.meta.id}
            className={i > 0 ? "docs-break mt-12" : ""}
            aria-labelledby={`print-${i}`}
          >
            <h1 id={`print-${i}`} className="text-3xl font-bold text-ink">
              {d.meta.title}
            </h1>
            <p className="mt-1 text-muted">{d.meta.summary}</p>
            <div className="mt-4">
              <DocBody doc={d} lang={lang} />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
