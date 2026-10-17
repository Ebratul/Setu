import { expect, test } from "@playwright/test";

test("Rahima asks about cash in Bangla and gets a cash-flow card, then uses the drawer", async ({
  page,
}) => {
  await page.goto("/login");
  await page
    .getByRole("button", { name: /Rahima/ })
    .first()
    .click();
  await page.waitForURL(/\/app$/);

  await page.goto("/app/chat");
  await page.getByLabel("বাংলা").check();
  const box = page.getByLabel("সেতুকে বার্তা");
  await box.fill("আমার কি এই মাসে cash কম পড়বে?");
  await box.press("Enter");

  const card = page.locator('[data-card-type="cashflow"]').first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card).toContainText("1,560.00");
  await expect(page.getByText("সিমুলেটেড").first()).toBeVisible();
  await expect(page).toHaveURL(/\/app\/chat\?thread=/);

  // Floating drawer from the dashboard.
  await page.goto("/app");
  await page.getByRole("button", { name: "সেতুকে জিজ্ঞাসা করুন" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "আমার কি এই মাসে cash কম পড়বে?" }).click();
  await expect(
    dialog.locator('[data-card-type="cashflow"]').first(),
  ).toContainText("1,560.00", { timeout: 30_000 });
  await expect(
    dialog.getByRole("link", { name: /পূর্ণ চ্যাট খুলুন/ }),
  ).toHaveAttribute("href", /\/app\/chat\?thread=/);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("a knowledge-base answer shows a citation chip and a Sources entry", async ({
  page,
}) => {
  await page.goto("/login");
  await page
    .getByRole("button", { name: /Rahima/ })
    .first()
    .click();
  await page.waitForURL(/\/app$/);
  await page.goto("/app/chat");
  const box = page.getByLabel("Message to Setu");
  await box.fill("What does FOB mean?");
  await box.press("Enter");
  const chip = page.getByRole("button", { name: /^Source S1/ });
  await expect(chip).toHaveText("[S1]", { timeout: 30_000 });
  const sources = page.getByTestId("sources");
  await expect(sources).toContainText("Incoterms basics");
  await chip.click();
  await expect(sources.locator('[data-cite-entry="S1"]')).toHaveAttribute(
    "data-highlighted",
    "true",
  );
});
