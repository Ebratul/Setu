import { availableLangs, listDocs } from "./content";
import { SECTIONS, type DocLang, type DocMeta } from "./types";

export type NavSection = { section: (typeof SECTIONS)[number]; items: { id: string; title: string; roles: DocMeta["roles"] }[] };

export function buildNav(lang: DocLang): NavSection[] {
  const docs = listDocs(lang);
  return SECTIONS.map((section) => ({
    section,
    items: docs.filter((d) => d.meta.section === section).map((d) => ({ id: d.meta.id, title: d.meta.title, roles: d.meta.roles })),
  })).filter((s) => s.items.length > 0);
}

export function langsByPage(): Record<string, DocLang[]> {
  const out: Record<string, DocLang[]> = {};
  for (const d of listDocs("en")) out[d.meta.id] = availableLangs(d.meta.id);
  for (const lang of ["bn", "zh"] as const) for (const d of listDocs(lang)) out[d.meta.id] ??= availableLangs(d.meta.id);
  return out;
}

/** Reading order across all sections, for previous / next links. */
export function readingOrder(lang: DocLang): DocMeta[] {
  return listDocs(lang).map((d) => d.meta);
}
