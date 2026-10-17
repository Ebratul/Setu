import { expect, test } from "@playwright/test";

// Karim (Dhaka Stitch Works) trades with Guangzhou Huameng (SETU-2026-0005); Rahima does not.
test("Karim sees Huameng flagged Warning and its failing checks", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Karim/ }).first().click();
  await page.waitForURL(/\/app(\/|$)/);

  await page.goto("/app/suppliers");
  await expect(page.getByRole("heading", { level: 1, name: "Suppliers" })).toBeVisible();
  const row = page.getByTestId("supplier-row").filter({ hasText: "Guangzhou Huameng" });
  await expect(row).toBeVisible();
  await expect(row.getByTestId("kyb-badge")).toHaveAttribute("data-status", "WARNING");

  await row.getByRole("link", { name: /Guangzhou Huameng/ }).click();
  await page.waitForURL(/\/app\/suppliers\/[0-9a-f-]+$/);
  await expect(page.getByTestId("kyb-badge").first()).toHaveAttribute("data-status", "WARNING");
  const failing = page.locator('[data-testid="kyb-check"][data-status="FAIL"]');
  await expect(failing.first()).toBeVisible();
  expect(await failing.count()).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("button", { name: "Re-run KYB" })).toBeVisible();

  await page.goto("/app/orders/SETU-2026-0005");
  await expect(page.getByRole("heading", { name: "Supplier check" })).toBeVisible();
});

test("Rahima does not see Huameng", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Rahima/ }).first().click();
  await page.waitForURL(/\/app(\/|$)/);
  await page.goto("/app/suppliers");
  await expect(page.getByTestId("supplier-row").first()).toBeVisible();
  await expect(page.getByText("Guangzhou Huameng")).toHaveCount(0);
});
