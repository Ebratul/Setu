import { expect, test } from "@playwright/test";

// Read-only walk over the seeded SETU-2026-0001 (M1 funded, 3 milestones) as buyer and as supplier.
test("Rahima opens SETU-2026-0001 and sees 3 milestones and the escrow card", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Rahima/ }).first().click();
  await page.waitForURL(/\/app$/);

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Deals" }).click();
  await page.waitForURL(/\/app\/deals$/);
  await expect(page.getByRole("heading", { level: 1, name: "Deals" })).toBeVisible();
  const row = page.getByTestId("deal-row").filter({ hasText: "SETU-2026-0001" });
  await expect(row).toBeVisible();
  await expect(row.getByTestId("kyb-badge")).toBeVisible();

  await row.getByRole("link", { name: "SETU-2026-0001" }).click();
  await page.waitForURL(/\/app\/deals\/SETU-2026-0001$/);
  await expect(page.getByRole("heading", { level: 1, name: "SETU-2026-0001" })).toBeVisible();
  await expect(page.getByTestId("milestone")).toHaveCount(3);
  await expect(page.getByTestId("escrow-card")).toBeVisible();
  await expect(page.getByTestId("escrow-balance")).toContainText("$");
  await expect(page.getByText("Simulated").first()).toBeVisible();
  await expect(page.getByTestId("ledger-table")).toBeVisible();

  await page.getByRole("tab", { name: "Activity" }).click();
  await expect(page.getByRole("heading", { name: "Activity" })).toBeVisible();

  await page.goto("/app/orders/SETU-2026-0001");
  await page.waitForURL(/\/app\/deals\/SETU-2026-0001$/);
  await page.goto("/app/orders/SETU-2026-0001/analysis");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("SETU-2026-0001");
});

test("supplier Huaxin lands in the portal and sees the deal with funds secured", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Wang Lei/ }).first().click();
  await page.waitForURL(/\/supplier$/);
  await expect(page.getByRole("heading", { level: 1, name: /Orders/ })).toBeVisible();

  const order = page.getByTestId("supplier-order").filter({ hasText: "SETU-2026-0001" });
  await expect(order).toBeVisible();
  await order.getByRole("link", { name: "SETU-2026-0001" }).click();
  await page.waitForURL(/\/supplier\/SETU-2026-0001$/);
  await expect(page.getByTestId("funds-secured")).toContainText("Funds secured in escrow: $");
  await expect(page.getByTestId("milestone")).toHaveCount(3);
  await expect(page.getByTestId("action-confirm")).toBeVisible();
  // Buyer-private data stays out of the portal.
  await expect(page.getByText("Supplier check")).toHaveCount(0);

  await page.goto("/app");
  await page.waitForURL(/\/supplier$/);
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toHaveCount(0);

  await page.getByLabel("中文").check();
  await expect(page.getByTestId("supplier-order").first()).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("订单");
});
