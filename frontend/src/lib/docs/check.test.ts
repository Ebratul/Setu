/**
 * Documentation quality gate (`pnpm docs:check`): route coverage, links + anchors, i18n completeness,
 * screenshot alt text and requirement mapping. Fails when the docs drift from the app.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { getDoc, listDocs, type DocFile } from "./content";
import { compileMdx } from "./mdx";
import { DOC_LANGS, routeMatches, type DocLang } from "./types";

const APP_DIR = path.join(process.cwd(), "src", "app");
const REQUIREMENTS = path.join(process.cwd(), "..", "docs", "REQUIREMENTS.md");
const MAP_FILE = path.join(process.cwd(), "content", "docs", "requirements-map.json");

/** Languages that must have every page of a section (EN is the source). */
const ZH_SECTIONS = new Set(["supplier", "getting-started"]);
/** Routes that need no guide page: the docs themselves. */
const EXEMPT = (r: string) => r === "/docs" || r.startsWith("/docs/");

function appRoutes(): string[] {
  const out: string[] = [];
  function walk(dir: string, segs: string[]) {
    for (const name of readdirSync(dir)) {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) {
        const group = /^\(.*\)$/.test(name);
        walk(full, group ? segs : [...segs, name]);
      } else if (name === "page.tsx") {
        out.push("/" + segs.join("/"));
      }
    }
  }
  walk(APP_DIR, []);
  return out.map((r) => (r === "/" ? r : r.replace(/\/$/, ""))).sort();
}

const ROUTES = appRoutes();
const en = listDocs("en");
const ids = new Set(en.map((d) => d.meta.id));

function bodyLinks(d: DocFile): string[] {
  const links = [...d.body.matchAll(/\]\((\/[^)\s]*)\)/g)].map((m) => m[1]);
  links.push(...[...d.body.matchAll(/href="(\/[^"]*)"/g)].map((m) => m[1]));
  if (d.meta.tryIt) links.push(d.meta.tryIt);
  return links;
}

function screenshotRoutes(d: DocFile): string[] {
  return [...d.body.matchAll(/<Screenshot\b[^>]*?\broute="([^"]+)"/g)].map((m) => m[1]);
}

const isRoute = (p: string) => ROUTES.some((r) => routeMatches(r, p.split("#")[0].split("?")[0]));

describe("coverage", () => {
  it("every app route is documented by at least one page", () => {
    const documented = new Set(en.flatMap((d) => d.meta.routes));
    const missing = ROUTES.filter((r) => !EXEMPT(r) && !documented.has(r));
    expect(missing, `routes without a guide page: ${missing.join(", ")}`).toEqual([]);
  });

  it("every documented route exists in the app", () => {
    const bad = en.flatMap((d) => d.meta.routes.filter((r) => !ROUTES.includes(r)).map((r) => `${d.meta.id}: ${r}`));
    expect(bad).toEqual([]);
  });

  it("every requirement in docs/REQUIREMENTS.md maps to existing guide pages", () => {
    const req = readFileSync(REQUIREMENTS, "utf8");
    const wanted = [...req.matchAll(/^\|\s*((?:FR|SR|NFR)-\d+)\s*\|/gm)].map((m) => m[1]);
    const map = JSON.parse(readFileSync(MAP_FILE, "utf8")) as Record<string, string[]>;
    const problems: string[] = [];
    for (const id of wanted) {
      const pages = map[id];
      if (!pages?.length) problems.push(`${id}: not mapped`);
      else for (const p of pages) if (!ids.has(p)) problems.push(`${id}: missing page ${p}`);
    }
    expect(problems).toEqual([]);
  });
});

describe("i18n completeness", () => {
  it("BN has every page, ZH has the supplier guide and getting started", () => {
    const missing: string[] = [];
    for (const d of en) {
      if (!getDoc("bn", d.meta.id)) missing.push(`bn/${d.meta.id}`);
      if (ZH_SECTIONS.has(d.meta.section) && !getDoc("zh", d.meta.id)) missing.push(`zh/${d.meta.id}`);
    }
    expect(missing).toEqual([]);
  });

  it("translations keep the same order, roles, routes and heading anchors", async () => {
    const problems: string[] = [];
    for (const d of en) {
      const base = (await compileMdx(d.body)).toc.map((t) => t.id).join(",");
      for (const lang of ["bn", "zh"] as DocLang[]) {
        const o = getDoc(lang, d.meta.id);
        if (!o) continue;
        const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
        if (o.meta.order !== d.meta.order) problems.push(`${lang}/${d.meta.id}: order`);
        if (!same(o.meta.roles, d.meta.roles)) problems.push(`${lang}/${d.meta.id}: roles`);
        if (!same(o.meta.routes, d.meta.routes)) problems.push(`${lang}/${d.meta.id}: routes`);
        const ids2 = (await compileMdx(o.body)).toc.map((t) => t.id).join(",");
        if (ids2 !== base) problems.push(`${lang}/${d.meta.id}: heading ids differ from en`);
      }
    }
    expect(problems).toEqual([]);
  });
});

describe("links and screenshots", () => {
  it("internal links resolve (docs pages, anchors and app routes)", async () => {
    const problems: string[] = [];
    const anchors = new Map<string, Set<string>>();
    for (const lang of DOC_LANGS) {
      for (const d of listDocs(lang)) {
        anchors.set(`${lang}/${d.meta.id}`, new Set((await compileMdx(d.body)).toc.map((t) => t.id)));
      }
    }
    for (const lang of DOC_LANGS) {
      for (const d of listDocs(lang)) {
        for (const link of bodyLinks(d)) {
          const m = /^\/docs\/(en|bn|zh)\/([\w-]+\/[\w-]+)(?:#(.+))?$/.exec(link);
          if (link.startsWith("/docs")) {
            if (!m) {
              if (link !== "/docs" && !/^\/docs\/(en|bn|zh)$/.test(link)) problems.push(`${lang}/${d.meta.id}: bad docs link ${link}`);
              continue;
            }
            const set = anchors.get(`${m[1]}/${m[2]}`) ?? (m[1] !== "en" ? anchors.get(`en/${m[2]}`) : undefined);
            if (!set) problems.push(`${lang}/${d.meta.id}: missing page ${link}`);
            else if (m[3] && !set.has(m[3])) problems.push(`${lang}/${d.meta.id}: missing anchor ${link}`);
          } else if (link.startsWith("/app") || link.startsWith("/supplier") || link.startsWith("/demo") || link === "/verify") {
            if (!isRoute(link)) problems.push(`${lang}/${d.meta.id}: no such route ${link}`);
          }
        }
        for (const r of d.meta.related) if (!ids.has(r)) problems.push(`${lang}/${d.meta.id}: related ${r} does not exist`);
        for (const r of screenshotRoutes(d)) if (!isRoute(r)) problems.push(`${lang}/${d.meta.id}: screenshot route ${r}`);
      }
    }
    expect(problems).toEqual([]);
  });

  it("every Screenshot has alt text, a name and a route", () => {
    const problems: string[] = [];
    for (const lang of DOC_LANGS) {
      for (const d of listDocs(lang)) {
        for (const m of d.body.matchAll(/<Screenshot\b([\s\S]*?)\/>/g)) {
          const attrs = m[1];
          if (!/\balt="[^"]{4,}"/.test(attrs)) problems.push(`${lang}/${d.meta.id}: screenshot without alt`);
          if (!/\bname="[^"]+"/.test(attrs)) problems.push(`${lang}/${d.meta.id}: screenshot without name`);
          if (!/\broute="[^"]+"/.test(attrs)) problems.push(`${lang}/${d.meta.id}: screenshot without route`);
        }
      }
    }
    expect(problems).toEqual([]);
  });

  it("feature pages use the standard template anchors", async () => {
    const problems: string[] = [];
    for (const d of en) {
      if (!["buyer", "supplier", "admin"].includes(d.meta.section)) continue;
      const toc = (await compileMdx(d.body)).toc.map((t) => t.id);
      for (const id of ["what-it-is", "how-to", ...(d.meta.tryIt ? ["try-it"] : [])]) if (!toc.includes(id)) problems.push(`${d.meta.id}: #${id}`);
    }
    expect(problems).toEqual([]);
  });
});
