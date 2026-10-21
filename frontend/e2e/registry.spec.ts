import { expect, test } from "@playwright/test";

// Needs the seeded demo (SETU-2026-0001 with an invoice already pledged as collateral to Lender A).
test("judge: Lender B is blocked on the registered invoice, and the registry lists Lender A", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Demo Judge/ }).first().click();
  await page.waitForURL(/\/app$/);

  await page.goto("/app/deals/SETU-2026-0001");
  await expect(page.getByRole("heading", { level: 1, name: "SETU-2026-0001" })).toBeVisible();
  await page.getByRole("button", { name: "Try to finance this invoice at Lender B" }).click();
  await expect(page.getByTestId("lender-check-blocked")).toContainText("Lender B would reject this");
  await expect(page.getByTestId("lender-check-blocked")).toContainText("Lender A");

  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Registry" }).click();
  await page.waitForURL(/\/app\/admin\/registry$/);
  await expect(page.getByRole("heading", { level: 1, name: "Document hash registry" })).toBeVisible();
  await expect(page.getByTestId("registry-row").filter({ hasText: "Lender A" }).first()).toBeVisible();
});
