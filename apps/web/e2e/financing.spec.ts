import { expect, test } from "@playwright/test";

test("Rahima finances the shortfall and the alert disappears", async ({
  page,
}) => {
  await page.goto("/login");
  await page
    .getByRole("button", { name: /Rahima/ })
    .first()
    .click();
  await page.waitForURL(/\/app$/);

  const shortfall = page.locator('[data-alert-type="SHORTFALL"]').first();
  await expect(shortfall).toContainText("1,560");
  await shortfall.getByRole("link").click();

  await page.waitForURL(/\/app\/financing/);
  await expect(page.getByText("1,560").first()).toBeVisible();
  const recommended = page.locator(
    '[data-testid="option-card"][data-recommended="true"]',
  );
  await expect(recommended).toContainText("Recommended");

  await recommended.getByRole("button", { name: /Apply/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Confirm application" }).click();
  await expect(dialog.getByText(/^Approved \(simulated\)/)).toBeVisible({
    timeout: 15_000,
  });

  await page.goto("/app");
  await page.waitForLoadState("networkidle");
  await expect(
    page.locator('[data-alert-type="SHORTFALL"]').filter({ hasText: "1,560" }),
  ).toHaveCount(0);
});
