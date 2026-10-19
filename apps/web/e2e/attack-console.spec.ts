import { expect, test } from "@playwright/test";

// Needs the seeded demo and the agent running; the judge account may use the attack console.
test("judge runs a hidden-text attack with defences on and sees it blocked", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Demo Judge/ }).first().click();
  await page.waitForURL(/\/app/);

  await page.goto("/demo/attack-console");
  await expect(page.getByRole("heading", { level: 1, name: "Prompt-injection attack console" })).toBeVisible();

  await page.getByRole("button", { name: /Hidden white text/ }).first().click();
  await expect(page.getByRole("switch", { name: /Defences/ })).toHaveAttribute("aria-checked", "true");
  await page.getByRole("button", { name: "Run attack" }).click();

  await expect(page.getByTestId("pipeline-steps").getByRole("listitem")).toHaveCount(6, { timeout: 15_000 });
  await expect(page.getByTestId("result-text")).toContainText("Attack blocked", { timeout: 15_000 });
});
