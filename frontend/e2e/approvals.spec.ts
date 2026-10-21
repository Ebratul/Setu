import { expect, test, type Browser, type Page } from "@playwright/test";

// Needs the seeded demo (reset with E2E_RESET_DEMO=1 or `python -m seed.cli reset-demo`) and the agent running
// with DEMO_MODE=true and a short COOLING_OFF_SECONDS (30 in the dev setup). Run serially in file order.
test.describe.configure({ mode: "serial" });

async function loginAs(page: Page, name: RegExp) {
  await page.goto("/login");
  await page.getByRole("button", { name }).first().click();
}

async function newPage(browser: Browser, name: RegExp) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await loginAs(page, name);
  return { context, page };
}

test("Rahima rejects the email-origin Tier 3 request, then approves M1 in one tap", async ({ page }) => {
  await loginAs(page, /Rahima/);
  await page.waitForURL(/\/app$/);
  await page.goto("/app/approvals");
  await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();

  const emailCard = page
    .getByTestId("approval-card")
    .filter({ has: page.getByTestId("email-origin-note") });
  await expect(emailCard).toHaveCount(1);
  await expect(emailCard).toContainText("Setu never changes accounts from email");
  await emailCard.getByTestId("review-btn").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("approve-btn")).toBeDisabled();
  await expect(dialog.getByTestId("reject-btn")).toBeEnabled();
  await dialog.getByTestId("reject-btn").click();
  await expect(page.getByTestId("toast").first()).toContainText("rejected");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(emailCard).toHaveCount(0);

  const m1 = page.getByTestId("approval-card").filter({ hasText: "Release a payment tranche" });
  await expect(m1).toContainText("SETU-2026-0001");
  await expect(m1.getByTestId("tier-badge")).toHaveAttribute("data-tier", "2");
  await m1.getByTestId("review-btn").click();
  const t2 = page.getByTestId("tier2-dialog");
  await expect(t2).toContainText("Simulated");
  await expect(t2.getByTestId("what-happens")).toContainText("moves from escrow");
  await t2.getByTestId("approve-btn").click();
  await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("toast").first()).toBeVisible();

  await page.goto("/app/deals/SETU-2026-0001");
  await expect(page.getByTestId("milestone").first().getByTestId("milestone-status")).toContainText("Released");
  await expect(page.getByTestId("approval-trail")).toBeVisible();
});

test("supplier changes the payout account; buyer confirms with the code from the demo phone", async ({ browser }) => {
  test.setTimeout(180_000);
  const last4 = String(Math.floor(1000 + Math.random() * 9000));
  const number = `62220${Date.now().toString().slice(-8)}${last4}`;

  const supplier = await newPage(browser, /Wang Lei/);
  const sp = supplier.page;
  await sp.waitForURL(/\/supplier$/);
  await sp.goto("/supplier/SETU-2026-0001");
  const form = sp.getByTestId("change-account-form");
  await form.getByLabel(/Bank name/).fill("Bank of Hong Kong");
  await form.getByLabel(/Bank country/).fill("HK");
  await form.getByLabel(/Account number/).fill(number);
  await form.getByLabel(/Account holder/).fill("Shaoxing Huaxin Textile Co., Ltd.");
  await form.getByTestId("submit-change").click();
  await expect(sp.getByTestId("change-stage").first()).toContainText("Waiting for buyer verification");
  await expect(sp.getByTestId("change-tracker").locator("li[data-state]").first()).toBeVisible();

  const buyer = await newPage(browser, /Rahima/);
  const bp = buyer.page;
  await bp.waitForURL(/\/app$/);
  await bp.goto("/app/approvals");
  const card = bp
    .getByTestId("approval-card")
    .filter({ hasText: "receiving account" })
    .filter({ hasNot: bp.getByTestId("email-origin-note") });
  await expect(card).toHaveCount(1);
  await card.getByTestId("review-btn").click();
  const dialog = bp.getByTestId("tier3-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByTestId("why-pause")).toContainText("protects you from rushed payment-redirection scams");
  await expect(dialog.getByTestId("approve-btn")).toBeDisabled();

  const phone = bp.getByTestId("demo-phone");
  await expect(phone).toContainText("Simulated SMS");
  await expect(phone.getByTestId("sms-code")).toHaveText(/^\d{6}$/, { timeout: 15_000 });
  const code = (await phone.getByTestId("sms-code").textContent())!.trim();
  await dialog.getByLabel("Digit 1 of 6").fill(code);
  await expect(dialog.getByLabel("Digit 6 of 6")).toHaveValue(code[5]);
  // The ring finishes after the cooling-off (30 s in this backend).
  await expect(dialog.getByTestId("cooling-ring")).toHaveAttribute("data-done", "true", { timeout: 90_000 });
  await expect(dialog.getByTestId("approve-btn")).toBeEnabled();
  await dialog.getByTestId("approve-btn").click();
  await expect(bp.getByRole("dialog")).toHaveCount(0, { timeout: 20_000 });

  await bp.goto("/app/deals/SETU-2026-0001");
  await expect(bp.getByText(`****${last4}`)).toBeVisible();
  await expect(sp.getByTestId("change-stage").first()).toContainText("Approved", { timeout: 20_000 });

  await supplier.context.close();
  await buyer.context.close();
});

test("email check blocks the demo redirection email", async ({ page }) => {
  await loginAs(page, /Rahima/);
  await page.waitForURL(/\/app$/);
  await page.goto("/app/inbox/email-check");
  await expect(page.getByRole("heading", { level: 1, name: "Check a suspicious email" })).toBeVisible();
  await page.getByTestId("load-demo-email").click();
  await expect(page.getByLabel("Email text")).not.toHaveValue("");
  await page.getByTestId("check-email").click();
  const result = page.getByTestId("email-result");
  await expect(result).toHaveAttribute("data-verdict", "BLOCKED");
  await expect(result).toContainText("Setu never changes payment accounts based on email");
  await expect(page.getByTestId("account-unchanged")).toBeVisible();
  await expect(result.getByRole("listitem").first()).toBeVisible();
});

test("scam simulator explains the large-advance dry run and the redirection email", async ({ page }) => {
  await loginAs(page, /Rahima/);
  await page.waitForURL(/\/app$/);
  await page.goto("/demo/scam-simulator");
  await expect(page.getByRole("heading", { level: 1, name: "Scam simulator" })).toBeVisible();
  await page.getByTestId("sim-large-advance").click();
  const res = page.getByTestId("sim-result");
  await expect(res).toHaveAttribute("data-scenario", "large-advance");
  await expect(res.getByTestId("tier-badge")).toBeVisible();
  await page.getByTestId("sim-redirect-email").click();
  await expect(page.getByTestId("sim-result")).toHaveAttribute("data-scenario", "redirect-email");
  await expect(page.getByTestId("email-result")).toContainText("Setu never changes payment accounts based on email");
});

test("notification bell shows unread activity and clears it on open", async ({ page }) => {
  await loginAs(page, /Rahima/);
  await page.waitForURL(/\/app$/);
  const bell = page.getByTestId("bell");
  await expect(bell).toBeVisible();
  await bell.click();
  await expect(page.getByRole("region", { name: "Recent activity" }).getByRole("listitem").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("region", { name: "Recent activity" })).toHaveCount(0);
  await expect(bell).toBeFocused();
  await expect(page.getByTestId("bell-count")).toHaveCount(0);
});
