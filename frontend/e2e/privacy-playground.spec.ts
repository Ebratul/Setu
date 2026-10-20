import { expect, test } from "@playwright/test";

// Needs the seeded demo and the agent running; the judge account may use the dry-run endpoint.
test("judge opens the privacy playground, sees an NID highlighted and the masked payload", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Demo Judge/ }).first().click();
  await page.waitForURL(/\/app/);

  await page.goto("/demo/privacy-playground");
  await expect(page.getByRole("heading", { level: 1, name: "Privacy Gateway playground" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Text to protect" })).toHaveValue(/NID 1990123456789/);

  const live = page.getByTestId("live-source");
  await expect(live.locator('mark[data-type="NID"]').first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Send to AI (dry run)" }).click();
  await expect(page.getByTestId("pane-masked")).toContainText("⟦NID_1⟧", { timeout: 15_000 });
  await expect(page.getByTestId("pane-restored")).toContainText("1990123456789");
});
