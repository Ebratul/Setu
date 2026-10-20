import Link from "next/link";
import { Suspense } from "react";
import { notFound } from "next/navigation";

import { DocsHomeText } from "@/components/docs/DocsHomeText";
import { buildNav } from "@/lib/docs/nav";
import { DOC_LANGS, isDocLang } from "@/lib/docs/types";

export function generateStaticParams() {
  return DOC_LANGS.map((lang) => ({ lang }));
}

export default function DocsHome({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  return (
    <Suspense fallback={null}>
      <DocsHomeContent params={params} />
    </Suspense>
  );
}

async function DocsHomeContent({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isDocLang(lang)) notFound();
  const nav = buildNav(lang);
  return (
    <div className="docs-print">
      <DocsHomeText />
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {nav.map((s) => (
          <section
            key={s.section}
            className="rounded-card border border-line bg-surface p-5 shadow-card"
            aria-labelledby={`home-${s.section}`}
          >
            <DocsHomeText section={s.section} headingId={`home-${s.section}`} />
            <ul className="mt-3 space-y-1">
              {s.items.map((i) => (
                <li key={i.id}>
                  <Link
                    href={`/docs/${lang}/${i.id}`}
                    className="inline-flex min-h-10 items-center rounded font-semibold text-brand-text underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:outline-none"
                  >
                    {i.title}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
