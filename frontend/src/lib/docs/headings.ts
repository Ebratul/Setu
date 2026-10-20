import type { Element, Root, Text } from "hast";
import { visit } from "unist-util-visit";

import type { TocItem } from "./types";

const EXPLICIT = /\s*\{#([\w-]+)\}\s*$/;

function textOf(node: Element): string {
  let out = "";
  visit(node, "text", (t: Text) => {
    out += t.value;
  });
  return out.trim();
}

/** Strips a trailing `{#id}` from h2/h3 text into the heading id and collects the table of contents. */
export function rehypeHeadingIds() {
  return () => (tree: Root) => {
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "h2" && node.tagName !== "h3") return;
      const last = node.children[node.children.length - 1];
      if (last && last.type === "text") {
        const m = EXPLICIT.exec(last.value);
        if (m) {
          last.value = last.value.replace(EXPLICIT, "");
          node.properties = { ...node.properties, id: m[1] };
        }
      }
    });
    return undefined;
  };
}

/** Run after rehype-slug so every heading already has its final id. */
export function rehypeCollectToc(toc: TocItem[]) {
  return () => (tree: Root) => {
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "h2" && node.tagName !== "h3") return;
      const id = node.properties?.id;
      if (typeof id !== "string") return;
      toc.push({ id, text: textOf(node), depth: node.tagName === "h2" ? 2 : 3 });
    });
  };
}
