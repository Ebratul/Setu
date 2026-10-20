import { describe, expect, it } from "vitest";

import { listDocs, plainText } from "./content";
import { compileMdx } from "./mdx";
import { buildIndex, tokenize } from "./search";
import { DOC_LANGS, pickDocForRoute, routeMatches } from "./types";

describe("docs content", () => {
  for (const lang of DOC_LANGS) {
    for (const { meta, body } of listDocs(lang)) {
      it(`${lang}/${meta.id} compiles with required front matter`, async () => {
        expect(meta.title).not.toBe(meta.id);
        expect(meta.summary.length).toBeGreaterThan(5);
        expect(meta.roles.length).toBeGreaterThan(0);
        const { toc } = await compileMdx(body);
        const ids = toc.map((t) => t.id);
        expect(new Set(ids).size).toBe(ids.length);
        for (const t of toc) expect(t.text).not.toMatch(/\{#/);
      });
    }
  }
});

describe("route matching", () => {
  it("matches dynamic segments and prefers specific patterns", () => {
    expect(routeMatches("/app/deals/[id]", "/app/deals/SETU-1")).toBe(true);
    expect(routeMatches("/app/deals/[id]", "/app/deals/new")).toBe(true);
    expect(routeMatches("/app/deals", "/app/deals/SETU-1")).toBe(false);
    const hit = pickDocForRoute(
      [
        { pattern: "/app/deals/[id]", id: "buyer/deal-detail" },
        { pattern: "/app/deals/new", id: "buyer/creating-an-order" },
      ],
      "/app/deals/new",
    );
    expect(hit?.id).toBe("buyer/creating-an-order");
  });
});

describe("search", () => {
  const rec = (id: string, title: string, text: string) => ({
    id, title, summary: "", section: "buyer" as const, roles: ["buyer" as const], url: `/docs/en/${id}`, headings: "", text,
  });
  it("splits CJK into characters and keeps Bangla words", () => {
    expect(tokenize("托管付款")).toEqual(["托", "管", "付", "款"]);
    expect(tokenize("টাকা পাঠান")).toEqual(["টাকা", "পাঠান"]);
  });
  it("finds pages by OTP, Bangla and Chinese terms", () => {
    const idx = buildIndex([
      rec("buyer/approvals", "Approvals", "Tier 3 needs an OTP code and cooling-off"),
      rec("buyer/fx", "FX", "টাকা পাঠান rate lock"),
      rec("supplier/payout-account", "Payout", "更改收款账户需要买家批准"),
    ]);
    expect(idx.search("OTP")[0].id).toBe("buyer/approvals");
    expect(idx.search("পাঠান")[0].id).toBe("buyer/fx");
    expect(idx.search("收款账户")[0].id).toBe("supplier/payout-account");
  });
  it("strips MDX noise from plain text", () => {
    const t = plainText('## Hi \\{#a}\n<Callout type="tip">Use **OTP**</Callout>\n{/* REVIEW: x */}');
    expect(t).toContain("OTP");
    expect(t).not.toContain("REVIEW");
    expect(t).not.toContain("{#a}");
  });
});
