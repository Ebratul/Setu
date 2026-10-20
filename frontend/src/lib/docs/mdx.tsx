import { evaluate } from "@mdx-js/mdx";
import type { MDXComponents } from "mdx/types";
import * as runtime from "react/jsx-runtime";
import rehypeSlug from "rehype-slug";
import remarkGfm from "remark-gfm";

import { rehypeCollectToc, rehypeHeadingIds } from "./headings";
import type { TocItem } from "./types";

export type Compiled = { Content: (props: { components?: MDXComponents }) => React.ReactNode; toc: TocItem[] };

/** Compile one MDX body. `{#id}` heading anchors are resolved before rehype-slug fills in the rest. */
export async function compileMdx(body: string): Promise<Compiled> {
  const toc: TocItem[] = [];
  const options = {
    ...runtime,
    remarkPlugins: [remarkGfm],
    rehypePlugins: [rehypeHeadingIds(), rehypeSlug, rehypeCollectToc(toc)],
  };
  const mod = await evaluate(body, options as unknown as Parameters<typeof evaluate>[1]);
  return { Content: mod.default as Compiled["Content"], toc };
}
