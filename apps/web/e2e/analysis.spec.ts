import { expect, test } from "@playwright/test";

test("Rahima sees the landed cost for SETU-2026-0001", async ({ page }) => {
  await page.goto("/login");
  await page
    .getByRole("button", { name: /Rahima/ })
    .first()
    .click();
  await page.waitForURL(/\/app\//);
  await page.goto("/app/orders/SETU-2026-0001/analysis");
  await expect(page.getByText("11,200").first()).toBeVisible();
});
