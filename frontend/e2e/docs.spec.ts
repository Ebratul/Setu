import { expect, test } from "@playwright/test";

test("filter Supplier, open a page, switch to Chinese: same topic", async ({ page }) => {
  await page.goto("/docs/en");
  await page.getByTestId("docs-filter-supplier").click();
  await page.getByRole("link", { name: "Upload documents" }).first().click();
  await expect(page).toHaveURL(/\/docs\/en\/supplier\/upload-documents/);
  await page.getByTestId("docs-lang-zh").click();
  await expect(page).toHaveURL(/\/docs\/zh\/supplier\/upload-documents/);
  await expect(page.getByRole("heading", { level: 1, name: "上传单据" })).toBeVisible();
});

test("search 'OTP' finds the approvals guide", async ({ page }) => {
  await page.goto("/docs/en");
  await page.getByTestId("docs-search-open").click();
  await page.getByRole("combobox", { name: /search/i }).fill("OTP");
  await expect(page.getByRole("option", { name: /approvals/i }).first()).toBeVisible();
});

test("search works for Bangla terms", async ({ page }) => {
  await page.goto("/docs/bn");
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox").fill("OTP");
  await expect(page.getByRole("option").first()).toBeVisible();
});

test("'?' on /app/approvals opens the approvals guide", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Rahima/ }).first().click();
  await page.waitForURL(/\/app$/);
  await page.goto("/app/approvals");
  await page.getByTestId("help-button").click();
  await expect(page.getByTestId("help-frame")).toHaveAttribute("src", /\/docs\/\w+\/buyer\/approvals\?embed=1/);
  await expect(page.getByTestId("help-open-guide")).toBeVisible();
});

test("'Try it' deep-links into the guided demo step", async ({ page }) => {
  await page.goto("/docs/en/judge/guided-demo");
  const href = await page.getByTestId("try-it").first().getAttribute("href");
  expect(href).toMatch(/^\/demo/);
  await page.getByTestId("try-it").first().click();
  await expect(page).toHaveURL(/\/demo/);
});

test("download-as-PDF opens the print view of the whole guide", async ({ page }) => {
  await page.goto("/docs/en/buyer/dashboard");
  await page.getByTestId("docs-download-pdf").click();
  await expect(page).toHaveURL(/\/docs\/en\/guide\/buyer/);
  await expect(page.getByRole("button", { name: /download as pdf/i })).toBeVisible();
});

test("page feedback is remembered", async ({ page }) => {
  await page.goto("/docs/en/buyer/dashboard");
  await page.getByTestId("docs-vote-yes").click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Thank you for your feedback.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Thank you for your feedback.")).toBeVisible();
});
