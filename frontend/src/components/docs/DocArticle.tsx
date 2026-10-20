import { mdxComponents } from "@/components/docs/mdx";
import { compileMdx } from "@/lib/docs/mdx";
import type { DocFile } from "@/lib/docs/content";
import type { DocLang, TocItem } from "@/lib/docs/types";

type Props = { doc: DocFile; lang: DocLang; onToc?: (toc: TocItem[]) => void };

/** The compiled MDX body of one page. Also used (without chrome) by the print view. */
export async function DocBody({ doc, lang }: { doc: DocFile; lang: DocLang }) {
  const { Content } = await compileMdx(doc.body);
  return (
    <div className="docs-prose">
      <Content components={mdxComponents(lang)} />
    </div>
  );
}

export type { Props as DocArticleProps };
