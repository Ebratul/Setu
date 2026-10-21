import { expect, test } from "@playwright/test";

test("Rahima lands on the dashboard and sees the shortfall alert", async ({
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
});
