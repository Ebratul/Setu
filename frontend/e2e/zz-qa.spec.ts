import AxeBuilder from "@axe-core/playwright";
import { test } from "@playwright/test";
import { writeFileSync } from "node:fs";

const OUT = "/tmp/claude-1000/-data-Setu/f6c78fa0-e4ee-4d02-89fd-27f4055abb8c/scratchpad/shots";
const rows: string[] = [];
test.setTimeout(900000);

test("qa sweep", async ({ browser }) => {
  for (const vp of [{ w: 1440, h: 900 }, { w: 360, h: 780 }]) {
    for (const theme of ["light", "dark"]) {
      for (const lang of ["en", "bn", "zh"]) {
        const ctx = await browser.newContext({ viewport: { width: vp.w, height: vp.h }, baseURL: "http://localhost:3000" });
        await ctx.addInitScript(([l, th]) => {
          localStorage.setItem("setu_lang", l); localStorage.setItem("setu_theme", th);
          document.cookie = `setu_lang=${l}; path=/`;
        }, [lang, theme]);
        const page = await ctx.newPage();
        await page.goto("/login");
        await page.evaluate(async () => { await fetch("/api/auth/demo-login", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: "rahima@demo.setu" }) }); });
        const deals = await page.evaluate(async () => (await fetch("/api/deals")).json().catch(() => null));
        const dealId = Array.isArray(deals) ? deals[0]?.id : deals?.items?.[0]?.id;
        const paths = ["/", "/app", "/app/deals", dealId ? `/app/deals/${dealId}` : "", "/app/approvals", "/demo", "/demo/run"].filter(Boolean);
        for (const p of paths) {
          await page.goto(p, { waitUntil: "networkidle" }).catch(() => {});
          await page.waitForTimeout(600);
          const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
          const small = await page.evaluate(() => [...document.querySelectorAll("a,button")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.height < 24); }).length);
          const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
          const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}(${v.nodes.length})`);
          rows.push(`${vp.w} ${theme} ${lang} ${p.replace(/[0-9a-f-]{20,}/, "ID")} overflow=${overflow} tiny=${small} axe=${bad.join(",") || "ok"}`);
          if (lang === "bn" || theme === "dark" || vp.w === 360) await page.screenshot({ path: `${OUT}/${vp.w}-${theme}-${lang}-${p.replace(/[^a-z]/g, "_")}.png` });
        }
        await ctx.close();
      }
    }
  }
  writeFileSync(`${OUT}/report.txt`, rows.join("\n"));
});
