import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { ADMIN_EMAIL, AGENTS } from "./p30/env";
import {
  accessToken,
  badChecksumUscc,
  bdMobile,
  expectStep,
  field,
  fill,
  futureDate,
  googleSignIn,
  mockGoogleAccount,
  pdfFile,
  pngFile,
  randomDigits,
  totp,
  tr,
  uniqueEmail,
  useBackend,
  validUscc,
  type Lang,
} from "./p30/helpers";

// P30: Google sign-in (mock Neon Auth), role onboarding, verification gate. See playwright.p30.config.ts.
test.skip(!process.env.P30_E2E, "run with: pnpm --dir frontend exec playwright test -c playwright.p30.config.ts");

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// ------------------------------------------------------------------ wizard steps shared by the scenarios
async function chooseRole(page: Page, role: "BUYER" | "SUPPLIER" | "ADMIN", lang: Lang = "en") {
  await page.getByRole("radio", { name: new RegExp(`^${esc(tr(`ob.role.${role}`, lang))}`) }).check();
  await page.getByRole("button", { name: tr("ob.next", lang), exact: true }).click();
}

async function contactAndPhone(page: Page, mobile: string, lang: Lang = "en") {
  await fill(page, { full_name: "Rahima Test", designation: "Managing Director", mobile });
  await page.getByRole("button", { name: tr("ob.contact.save", lang), exact: true }).click();
  await page.getByRole("button", { name: tr("ob.phone.send", lang), exact: true }).click();
  const code = (await page.getByTestId("demo-code").textContent())?.trim() ?? "";
  expect(code).toMatch(/^\d{6}$/);
  await page.locator("#ob-otp").fill(code);
  await page.getByRole("button", { name: tr("ob.phone.verify", lang), exact: true }).click();
  await expect(page.getByText(tr("ob.phone.verified", lang))).toBeVisible();
  await page.getByRole("button", { name: tr("ob.next", lang), exact: true }).click();
}

async function upload(page: Page, type: string, file: ReturnType<typeof pngFile>) {
  await page.locator(`#ob-doc-${type}`).setInputFiles(file);
  await expect(page.getByText(file.name)).toBeVisible();
}

async function consentAndContinue(page: Page, lang: Lang = "en") {
  for (const k of ["ob.consent.terms", "ob.consent.privacy", "ob.consent.verify"]) {
    await page.getByRole("checkbox", { name: new RegExp(esc(tr(k, lang).slice(0, 20))) }).check();
  }
  await page.getByRole("button", { name: tr("ob.saveContinue", lang), exact: true }).click();
}

const buyerBusiness = (tag: string) => ({
  legal_name: `E2E Trading ${tag}`,
  trade_license_no: `TRAD-${randomDigits(8)}`,
  license_authority: "Dhaka South City Corporation",
  license_expiry: futureDate(2),
  irc_no: `BA-${randomDigits(7)}`,
  tin: randomDigits(12),
  "address.division": "Dhaka",
  "address.district": "Dhaka",
  "address.upazila": "Motijheel",
  "address.street": "12 Dilkusha C/A",
  main_import_goods: "LED lighting components",
});

async function fillBuyerBusiness(page: Page, tag: string) {
  await fill(page, buyerBusiness(tag));
  await field(page, "business_type").selectOption("TRADER");
  await field(page, "monthly_import_volume").selectOption("500K_2M_BDT");
  await page.getByRole("button", { name: tr("ob.saveContinue"), exact: true }).click();
}

/** Role -> contact -> OTP -> business -> documents -> consent -> submit, in English, as a buyer. */
async function onboardBuyer(page: Page, tag: string) {
  await chooseRole(page, "BUYER");
  await contactAndPhone(page, bdMobile());
  await fillBuyerBusiness(page, tag);
  await upload(page, "TRADE_LICENSE", pdfFile("trade-licence.pdf", `licence ${tag}`));
  await upload(page, "IRC", pngFile("irc.png"));
  await page.getByRole("button", { name: tr("ob.next"), exact: true }).click();
  await consentAndContinue(page);
  await page.getByRole("button", { name: tr("ob.submit"), exact: true }).click();
}

/** Admin path: role (allowlisted email) -> TOTP via the UI -> consent -> ACTIVE. Returns the TOTP secret. */
async function onboardAdmin(page: Page): Promise<string> {
  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding/);
  await chooseRole(page, "ADMIN");
  await expect(page.getByRole("heading", { level: 2, name: tr("ob.stepOf", "en", { n: 1, total: 2, name: tr("ob.step.security") }) })).toBeVisible();
  await page.getByRole("button", { name: tr("tp.start"), exact: true }).click();
  const secret = ((await page.getByTestId("totp-secret").textContent()) ?? "").replace(/\s/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  await page.locator("#tp-code").fill(totp(secret));
  await page.getByRole("button", { name: tr("tp.enable"), exact: true }).click();
  await page.getByRole("checkbox", { name: tr("tp.codes.confirm") }).check();
  await page.getByRole("button", { name: tr("tp.codes.done"), exact: true }).click();
  await expect(page.getByText(tr("ob.totp.on"))).toBeVisible();
  await consentAndContinue(page);
  // TOTP on + consent saved activates an admin at once; the wizard hands over to the app.
  await expect(page).toHaveURL(/\/app/);
  return secret;
}

// Seeded supplier (deterministic uuid5 from seed/parties.py): Shaoxing Huaxin Textile.
const DEAL_BODY = {
  supplier_id: "4870fe21-8ba6-5b4b-87c6-87f6b89bb105",
  title: "LED panel lights",
  hs_code: "9405.42",
  quantity: "1000",
  unit: "pcs",
  unit_price: "12.50",
  currency: "USD",
  incoterm: "FOB",
  port_of_loading: "Shenzhen",
  port_of_discharge: "Chattogram",
};

async function apiAs(page: Page, method: "get" | "post", path: string, data?: unknown) {
  const token = await accessToken(page);
  return page.request.fetch(`${AGENTS.A.url}${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}` },
    data: data as never,
  });
}

// ------------------------------------------------------------------ 1. buyer, end to end
test("buyer signs in with Google, onboards, waits for review, is blocked, then approved and can create a deal", async ({ page, context, browser, baseURL }) => {
  test.setTimeout(240_000);
  const tag = Date.now().toString(36).toUpperCase();
  await useBackend(context, "A");
  await mockGoogleAccount(context, { name: "Rahima Buyer" });

  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding$/);
  await expectStep(page, 1, 6, tr("ob.step.role"));

  await onboardBuyer(page, tag);

  // Status page and the locked money gate
  await expect(page).toHaveURL(/\/onboarding\/status/);
  await expect(page.getByText(tr("ost.pending.title"))).toBeVisible();
  const blocked = await apiAs(page, "post", "/deals", DEAL_BODY);
  expect(blocked.status()).toBe(403);
  const problem = (await blocked.json()) as { code?: string; detail?: string };
  expect(problem.code).toBe("ACCOUNT_NOT_VERIFIED");
  expect(problem.detail ?? "").toMatch(/verif/i);
  await page.goto("/app/deals/new");
  await expect(page.getByRole("heading", { level: 1, name: tr("dn.title") })).toBeVisible();
  await expect(page.getByText(tr("vb.review.title")).first()).toBeVisible();

  // Admin (allowlisted email, TOTP turned on through the UI) approves
  const adminCtx = await browser.newContext({ baseURL });
  const admin = await adminCtx.newPage();
  await useBackend(adminCtx, "A");
  await mockGoogleAccount(adminCtx, { email: ADMIN_EMAIL, name: "Setu Admin" });
  const secret = await onboardAdmin(admin);
  await admin.goto("/app/admin/verifications");
  await admin.getByRole("button", { name: `${tr("adm.onb.open")}: E2E Trading ${tag}`, exact: true }).click();
  await admin.getByRole("button", { name: tr("adm.onb.approve"), exact: true }).click();
  await admin.getByRole("dialog").getByRole("button", { name: tr("adm.onb.approve"), exact: true }).click();
  await admin.getByRole("dialog").getByLabel(new RegExp(esc(tr("vq.stepup.code")))).fill(totp(secret, 1));
  await admin.getByRole("dialog").getByRole("button", { name: tr("vq.stepup.confirm"), exact: true }).click();
  await expect(admin.getByText(tr("vq.done.approve", "en", { name: `E2E Trading ${tag}` }))).toBeVisible();
  await adminCtx.close();

  // Buyer is ACTIVE: the status page lets them through and a deal can be created
  await page.goto("/onboarding/status");
  await expect(page).toHaveURL(/\/app$/);
  const ok = await apiAs(page, "get", "/auth/me");
  expect(((await ok.json()) as { account_status: string }).account_status).toBe("ACTIVE");
  await page.getByRole("dialog").getByRole("button", { name: tr("wt.skip"), exact: true }).click(); // first-visit welcome tour
  // The new-deal screen no longer shows the lock, and the API accepts the deal.
  await page.goto("/app/deals/new");
  await expect(page.getByRole("heading", { level: 1, name: tr("dn.title") })).toBeVisible();
  await expect(page.getByText(tr("vb.review.title"))).toHaveCount(0);
  const created = await apiAs(page, "post", "/deals", DEAL_BODY);
  expect(created.status(), await created.text()).toBe(201);
  const { reference } = (await created.json()) as { reference: string };
  await page.goto("/app/deals");
  await expect(page.getByTestId("deal-row").filter({ hasText: reference })).toBeVisible();
});

test("a non-allowlisted email cannot pick the Administrator role", async ({ page, context }) => {
  await useBackend(context, "A");
  await mockGoogleAccount(context);
  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding$/);
  await chooseRole(page, "ADMIN");
  await expect(page.getByRole("alert").filter({ hasText: tr("ob.err.ROLE_NOT_ALLOWED") })).toBeVisible();
});

// ------------------------------------------------------------------ 2. supplier in Chinese
test("supplier onboards in Chinese up to submit with a valid USCC, bank details and documents", async ({ page, context }) => {
  test.setTimeout(180_000);
  const zh: Lang = "zh";
  const tag = Date.now().toString(36).toUpperCase();
  await useBackend(context, "A");
  await mockGoogleAccount(context, { name: "Wang Lei" });

  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.locator("label:visible", { hasText: "中文" }).first().click();
  await expect(page.locator("html")).toHaveAttribute("lang", "zh");
  await chooseRole(page, "SUPPLIER", zh);
  await contactAndPhone(page, `+86138${randomDigits(8)}`, zh);

  await fill(page, {
    legal_name_en: `Shenzhen E2E Lighting ${tag} Co., Ltd.`,
    legal_name_zh: "深圳测试照明有限公司",
    uscc: validUscc(),
    "address.province": "广东省",
    "address.city": "深圳市",
    "address.district": "南山区",
    business_scope: "LED照明产品的生产与出口",
    export_experience_years: "8",
    "bank.bank_name": "Industrial and Commercial Bank of China",
    "bank.holder_name": `Shenzhen E2E Lighting ${tag} Co., Ltd.`,
    "bank.account_no": `6222${randomDigits(12)}`,
    "bank.swift": "ICBKCNBJ",
  });
  await field(page, "bank.currency").selectOption("CNY");
  await page.getByRole("button", { name: tr("ob.saveContinue", zh), exact: true }).click();

  await upload(page, "BUSINESS_LICENSE", pdfFile("business-licence.pdf", `licence ${tag}`));
  await upload(page, "BANK_PROOF", pngFile("bank-proof.png"));
  await page.getByRole("button", { name: tr("ob.next", zh), exact: true }).click();
  await consentAndContinue(page, zh);
  await page.getByRole("button", { name: tr("ob.submit", zh), exact: true }).click();

  await expect(page).toHaveURL(/\/onboarding\/status/);
  await expect(page.getByText(tr("ost.pending.title", zh))).toBeVisible();
});

// ------------------------------------------------------------------ 3. unverified email
test("a sign-in whose email is not verified is rejected with the verify-email message", async ({ page, context }) => {
  await useBackend(context, "A");
  await mockGoogleAccount(context, { emailVerified: false });
  await googleSignIn(page);
  await expect(page.getByRole("alert").filter({ hasText: tr("auth.err.unverified") })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
  // No Setu account was created: the same identity cannot read anything
  const res = await page.request.get(`${AGENTS.A.url}/onboarding/me`, { headers: { Authorization: `Bearer ${await accessToken(page).catch(() => "none")}` } });
  expect([401, 403]).toContain(res.status());
});

// ------------------------------------------------------------------ 4. demo login list
test.describe("demo login list", () => {
  const heading = (page: Page) => page.getByRole("heading", { name: tr("lg.demoTitle") });

  test("is hidden when DEMO_MODE=false", async ({ page, context, request }) => {
    await useBackend(context, "B");
    await page.goto("/login");
    await expect(page.getByRole("button", { name: tr("lg.google"), exact: true })).toBeVisible();
    await expect(heading(page)).toHaveCount(0);
    expect((await request.get(`${AGENTS.B.url}/auth/demo-users`)).status()).toBe(404);
  });

  test("is hidden in neon mode with DEMO_MODE=true while the demo cookie flag is off", async ({ page, context, request }) => {
    await useBackend(context, "A");
    await page.goto("/login");
    await expect(page.getByRole("button", { name: tr("lg.google"), exact: true })).toBeVisible();
    await expect(heading(page)).toHaveCount(0);
    expect((await request.get(`${AGENTS.A.url}/auth/demo-users`)).status()).toBe(404);
  });

  test("is shown when DEMO_MODE=true and the demo cookie is enabled", async ({ page, context }) => {
    await useBackend(context, "C");
    await page.goto("/login");
    await expect(heading(page)).toBeVisible();
    await expect(page.getByRole("button", { name: /Rahima/ }).first()).toBeVisible();
  });
});

// ------------------------------------------------------------------ 5. inline validation
test("an invalid Bangladesh mobile number shows an inline error and nothing is saved", async ({ page, context }) => {
  await useBackend(context, "A");
  await mockGoogleAccount(context);
  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding$/);
  await chooseRole(page, "BUYER");
  await fill(page, { full_name: "Rahima Test", designation: "Managing Director", mobile: "0171234" });
  await page.getByRole("button", { name: tr("ob.contact.save"), exact: true }).click();
  const err = page.locator("#ob-mobile-error, [id^='ob-mobile'][id$='err'], [role='alert']").filter({ hasText: tr("ob.v.mobile") });
  await expect(err.first()).toBeVisible();
  await expect(field(page, "mobile")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByTestId("demo-code")).toHaveCount(0);
});

test("a USCC with a wrong checksum (and one of the wrong length) shows an inline error", async ({ page, context }) => {
  test.setTimeout(120_000);
  await useBackend(context, "A");
  await mockGoogleAccount(context);
  await googleSignIn(page);
  await expect(page).toHaveURL(/\/onboarding$/);
  await chooseRole(page, "SUPPLIER");
  await contactAndPhone(page, `+86139${randomDigits(8)}`);

  await field(page, "uscc").fill(badChecksumUscc());
  await page.getByRole("button", { name: tr("ob.saveContinue"), exact: true }).click();
  await expect(page.getByText(tr("ob.v.usccCheck")).first()).toBeVisible();
  await expect(field(page, "uscc")).toHaveAttribute("aria-invalid", "true");

  await field(page, "uscc").fill("9131000012345");
  await page.getByRole("button", { name: tr("ob.saveContinue"), exact: true }).click();
  await expect(page.getByText(tr("ob.v.usccLength")).first()).toBeVisible();

  await field(page, "uscc").fill(validUscc());
  await page.getByRole("button", { name: tr("ob.saveContinue"), exact: true }).click();
  await expect(page.getByText(tr("ob.v.usccCheck"))).toHaveCount(0);
  await expect(page.getByText(tr("ob.v.usccLength"))).toHaveCount(0);
});

// ------------------------------------------------------------------ accessibility
test.describe("axe", () => {
  const serious = (v: { impact?: string | null }[]) => v.filter((x) => x.impact === "serious" || x.impact === "critical");

  test("/login has no serious or critical violations", async ({ page, context }) => {
    await useBackend(context, "A");
    await page.goto("/login");
    await expect(page.getByRole("button", { name: tr("lg.google"), exact: true })).toBeVisible();
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(serious(violations), JSON.stringify(violations.map((v) => [v.id, v.nodes.map((n) => n.target)]))).toEqual([]);
  });

  test("/onboarding (role step) has no serious or critical violations", async ({ page, context }) => {
    await useBackend(context, "A");
    await mockGoogleAccount(context);
    await googleSignIn(page);
    await expect(page).toHaveURL(/\/onboarding$/);
    await expectStep(page, 1, 6, tr("ob.step.role"));
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(serious(violations), JSON.stringify(violations.map((v) => [v.id, v.nodes.map((n) => n.target)]))).toEqual([]);
  });
});

void uniqueEmail;
