import { readdirSync, readFileSync, existsSync } from "node:fs";
import path from "node:path";

import matter from "gray-matter";

import {
  DOC_LANGS,
  GUIDE_SECTIONS,
  SECTIONS,
  type DocLang,
  type DocMeta,
  type DocRole,
  type DocSection,
  type RouteMapEntry,
  type SearchRecord,
} from "./types";

export const CONTENT_DIR = path.join(process.cwd(), "content", "docs");

export type DocFile = { meta: DocMeta; body: string };

const cache = new Map<DocLang, DocFile[]>();

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

function parseFile(lang: DocLang, section: string, file: string): DocFile {
  const raw = readFileSync(path.join(CONTENT_DIR, lang, section, file), "utf8");
  const { data, content } = matter(raw);
  const id = `${section}/${file.replace(/\.mdx$/, "")}`;
  const meta: DocMeta = {
    id,
    lang,
    title: String(data.title ?? id),
    summary: String(data.summary ?? ""),
    section: (SECTIONS as readonly string[]).includes(String(data.section)) ? (data.section as DocSection) : (section as DocSection),
    order: Number(data.order ?? 999),
    roles: asStringArray(data.roles) as DocRole[],
    routes: asStringArray(data.routes),
    tryIt: data.tryIt ? String(data.tryIt) : undefined,
    related: asStringArray(data.related),
    updated: data.updated instanceof Date ? data.updated.toISOString().slice(0, 10) : String(data.updated ?? ""),
  };
  return { meta, body: content };
}

/** All pages of one language, sorted by section then order. */
export function listDocs(lang: DocLang): DocFile[] {
  const hit = cache.get(lang);
  if (hit) return hit;
  const root = path.join(CONTENT_DIR, lang);
  const out: DocFile[] = [];
  if (existsSync(root)) {
    for (const section of readdirSync(root, { withFileTypes: true })) {
      if (!section.isDirectory()) continue;
      for (const file of readdirSync(path.join(root, section.name))) {
        if (file.endsWith(".mdx")) out.push(parseFile(lang, section.name, file));
      }
    }
  }
  out.sort(
    (a, b) =>
      SECTIONS.indexOf(a.meta.section) - SECTIONS.indexOf(b.meta.section) || a.meta.order - b.meta.order || a.meta.id.localeCompare(b.meta.id),
  );
  cache.set(lang, out);
  return out;
}

export function getDoc(lang: DocLang, id: string): DocFile | undefined {
  return listDocs(lang).find((d) => d.meta.id === id);
}

/** The page in `lang`, or the English page when it has not been translated. */
export function getDocWithFallback(lang: DocLang, id: string): { doc: DocFile; fellBack: boolean } | undefined {
  const own = getDoc(lang, id);
  if (own) return { doc: own, fellBack: false };
  const en = getDoc("en", id);
  return en ? { doc: en, fellBack: true } : undefined;
}

export function availableLangs(id: string): DocLang[] {
  return DOC_LANGS.filter((l) => getDoc(l, id));
}

export function allDocIds(): string[] {
  return [...new Set(DOC_LANGS.flatMap((l) => listDocs(l).map((d) => d.meta.id)))];
}

export function guideDocs(lang: DocLang, section: DocSection): DocFile[] {
  return GUIDE_SECTIONS.includes(section) ? listDocs(lang).filter((d) => d.meta.section === section) : [];
}

export function routeMap(): RouteMapEntry[] {
  const seen = new Set<string>();
  const out: RouteMapEntry[] = [];
  for (const d of listDocs("en")) {
    for (const pattern of d.meta.routes) {
      if (seen.has(pattern)) continue;
      seen.add(pattern);
      out.push({ pattern, id: d.meta.id });
    }
  }
  return out;
}

const ATTR_TEXT = /\b(?:alt|caption|title|q|label)="([^"]*)"/g;

/** Readable plain text of an MDX body for the search index and the print view. */
export function plainText(body: string): string {
  const attrs = [...body.matchAll(ATTR_TEXT)].map((m) => m[1]).join(" ");
  const text = body
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\\\{#[\w-]+\}/g, " ")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*_>#|]/g, " ")
    .replace(/^\s*[-\d.]+\s+/gm, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `${text} ${attrs}`.trim();
}

function headingsOf(body: string): string {
  return [...body.matchAll(/^#{2,3}\s+(.+?)(?:\s*\\\{#[\w-]+\})?\s*$/gm)].map((m) => m[1]).join(" ");
}

export function searchRecords(lang: DocLang): SearchRecord[] {
  return listDocs(lang).map(({ meta, body }) => ({
    id: meta.id,
    title: meta.title,
    summary: meta.summary,
    section: meta.section,
    roles: meta.roles,
    url: `/docs/${lang}/${meta.id}`,
    headings: headingsOf(body),
    text: plainText(body),
  }));
}
