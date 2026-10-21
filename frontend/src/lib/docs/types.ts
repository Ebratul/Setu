export type DocLang = "en" | "bn" | "zh";
export type DocRole = "buyer" | "supplier" | "admin" | "judge";
export type DocFilter = "all" | DocRole;

export const DOC_LANGS: readonly DocLang[] = ["en", "bn", "zh"];
export const DOC_ROLES: readonly DocRole[] = ["buyer", "supplier", "admin", "judge"];

export const SECTIONS = [
  "getting-started",
  "buyer",
  "supplier",
  "admin",
  "judge",
  "security",
  "faq",
  "glossary",
] as const;
export type DocSection = (typeof SECTIONS)[number];

/** Sections that are the four role guides (each can be downloaded as one document). */
export const GUIDE_SECTIONS: readonly DocSection[] = ["buyer", "supplier", "admin"];

export type DocMeta = {
  /** `<section>/<name>`, identical in every language. */
  id: string;
  lang: DocLang;
  title: string;
  summary: string;
  section: DocSection;
  order: number;
  roles: DocRole[];
  routes: string[];
  tryIt?: string;
  related: string[];
  updated: string;
};

export type TocItem = { id: string; text: string; depth: 2 | 3 };

export type SearchRecord = {
  id: string;
  title: string;
  summary: string;
  section: DocSection;
  roles: DocRole[];
  url: string;
  headings: string;
  text: string;
};

export type RouteMapEntry = { pattern: string; id: string };

export function isDocLang(v: string): v is DocLang {
  return (DOC_LANGS as readonly string[]).includes(v);
}

export function docUrl(lang: DocLang, id: string, anchor?: string): string {
  return `/docs/${lang}/${id}${anchor ? `#${anchor}` : ""}`;
}

/** Match an app pathname against a documented route pattern such as `/app/deals/[id]`. */
export function routeMatches(pattern: string, pathname: string): boolean {
  const clean = pathname.split("?")[0].replace(/\/+$/, "") || "/";
  const re = new RegExp(
    "^" +
      pattern
        .replace(/[.*+?^${}()|\\]/g, "\\$&")
        .replace(/\[\.\.\.\w+\]/g, ".+")
        .replace(/\[\w+\]/g, "[^/]+") +
      "$",
  );
  return re.test(clean);
}

/** Most specific (longest, fewest wildcards) documented route for a pathname. */
export function pickDocForRoute(entries: RouteMapEntry[], pathname: string): RouteMapEntry | undefined {
  return entries
    .filter((e) => routeMatches(e.pattern, pathname))
    .sort((a, b) => b.pattern.replace(/\[\w+\]/g, "").length - a.pattern.replace(/\[\w+\]/g, "").length)[0];
}
