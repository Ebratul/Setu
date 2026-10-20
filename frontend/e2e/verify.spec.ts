import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

// Needs only the web app: the page reads files in the browser and ships its own public key.
const FIX = path.resolve(__dirname, "fixtures/audit");
const expected = JSON.parse(readFileSync(path.join(FIX, "expected.json"), "utf-8")) as Record<
  string,
  { ok: boolean; broken_seq: number | null; reason: string | null }
>;

async function check(page: import("@playwright/test").Page, log: string) {
  await page.goto("/verify");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByText("Advanced: use another public key (PEM)").click();
  await page.getByLabel("Public key file (.pem)").setInputFiles(path.join(FIX, "test-public-key.pem"));
  await page.getByLabel("Operation log (.jsonl)").setInputFiles(path.join(FIX, `${log}.jsonl`));
  return page.getByTestId("log-result");
}

test("good log verifies", async ({ page }) => {
  const result = await check(page, "good");
  await expect(result).toContainText("Verified ✓ 12 entries, seq 1..12");
  expect(expected.good.ok).toBe(true);
});

test("tampered amount breaks at the release entry", async ({ page }) => {
  const result = await check(page, "tampered-amount");
  await expect(result).toContainText(`Broken at seq ${expected["tampered-amount"].broken_seq}`);
  await expect(result).toContainText("entry contents no longer match the hash");
});

test("a deleted entry is reported at the missing seq", async ({ page }) => {
  const result = await check(page, "tampered-missing");
  await expect(result).toContainText(`Broken at seq ${expected["tampered-missing"].broken_seq}`);
});

test("nothing is sent to the network when a file is checked", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET" && !r.url().includes("__nextjs")) posts.push(r.url());
  });
  await check(page, "good");
  await expect(page.getByTestId("log-result")).toContainText("Verified");
  expect(posts).toEqual([]);
});

test("/verify has no detectable accessibility violations", async ({ page }) => {
  await page.goto("/verify");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  expect(res.violations).toEqual([]);
});
