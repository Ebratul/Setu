import MiniSearch from "minisearch";

import type { DocLang, SearchRecord } from "./types";

const CJK = /[㐀-鿿豈-﫿]/;

/** Splits on whitespace/punctuation (works for English and Bangla) and indexes every CJK character on its own. */
export function tokenize(text: string): string[] {
  const out: string[] = [];
  for (const word of text.split(/[\s\p{P}\p{S}]+/u)) {
    if (!word) continue;
    if (CJK.test(word)) {
      for (const ch of word) if (CJK.test(ch)) out.push(ch);
      const latin = word.replace(/[㐀-鿿豈-﫿]/g, " ").trim();
      if (latin) out.push(...latin.split(/\s+/));
    } else out.push(word);
  }
  return out;
}

export type DocIndex = {
  search: (query: string, limit?: number) => DocHit[];
};

export type DocHit = SearchRecord & { score: number };

export function buildIndex(records: SearchRecord[]): DocIndex {
  const mini = new MiniSearch<SearchRecord>({
    fields: ["title", "headings", "summary", "text"],
    storeFields: ["id", "title", "summary", "section", "roles", "url", "headings", "text"],
    tokenize,
    processTerm: (t) => t.toLowerCase(),
    searchOptions: {
      boost: { title: 4, headings: 2, summary: 1.5 },
      prefix: true,
      fuzzy: (term) => (term.length > 4 && !CJK.test(term) ? 0.2 : false),
      combineWith: "AND",
    },
  });
  mini.addAll(records);
  return {
    search(query, limit = 20) {
      const q = query.trim();
      if (!q) return [];
      const run = (combineWith: "AND" | "OR") => mini.search(q, { combineWith });
      let res = run("AND");
      if (res.length === 0) res = run("OR");
      return res.slice(0, limit).map((r) => ({
        id: r.id,
        title: r.title as string,
        summary: r.summary as string,
        section: r.section as SearchRecord["section"],
        roles: r.roles as SearchRecord["roles"],
        url: r.url as string,
        headings: r.headings as string,
        text: r.text as string,
        score: r.score,
      }));
    },
  };
}

const loaded = new Map<DocLang, Promise<DocIndex>>();

/** Fetch (once) and build the client-side index for a language. */
export function loadIndex(lang: DocLang): Promise<DocIndex> {
  let p = loaded.get(lang);
  if (!p) {
    p = fetch(`/docs-data/search/${lang}`)
      .then((r) => {
        if (!r.ok) throw new Error(`search index ${r.status}`);
        return r.json() as Promise<SearchRecord[]>;
      })
      .then(buildIndex);
    p.catch(() => loaded.delete(lang));
    loaded.set(lang, p);
  }
  return p;
}

/** A short excerpt around the first matching term. */
export function snippet(text: string, query: string, len = 140): string {
  const terms = tokenize(query.toLowerCase());
  const lower = text.toLowerCase();
  let at = -1;
  for (const t of terms) {
    at = lower.indexOf(t);
    if (at >= 0) break;
  }
  if (at < 0) return text.slice(0, len);
  const start = Math.max(0, at - 40);
  return (start > 0 ? "…" : "") + text.slice(start, start + len) + (start + len < text.length ? "…" : "");
}
