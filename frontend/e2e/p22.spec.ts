import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("landing: guided demo CTA starts the demo", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.getByRole("link", { name: /Run the guided demo/i }).first().click();
  await expect(page).toHaveURL(/\/demo/);
});

test("language switch persists across pages", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: /বাংলা/ }).first().check({ force: true });
  await expect(page.locator("html")).toHaveAttribute("lang", "bn");
  await page.goto("/accessibility");
  await expect(page.locator("html")).toHaveAttribute("lang", "bn");
});

test("dark mode toggle switches the theme and persists", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  const toggle = page.getByTestId("theme-toggle").first();
  await toggle.click(); // system -> light
  await toggle.click(); // light -> dark
  await expect(html).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", "dark");
});

test("command palette opens with Ctrl+K and navigates", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Rahima/i }).first().click();
  await page.waitForURL(/\/app/);
  const palette = page.getByTestId("command-palette");
  await page.getByTestId("open-palette").waitFor();
  await expect(async () => {
    await page.keyboard.press("Control+k");
    await expect(palette).toBeVisible({ timeout: 800 });
  }).toPass({ timeout: 10000 });
  await page.keyboard.type("cash");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/cashflow/);
});

test("public pages have no serious or critical axe violations", async ({ page }) => {
  for (const url of ["/", "/accessibility"]) {
    await page.goto(url);
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const bad = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(bad.map((v) => `${url} ${v.id}`)).toEqual([]);
  }
});
