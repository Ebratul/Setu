import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// /judges is public and needs only the web app (the status panel tolerates an unreachable agent).
async function setLang(page: Page, lang: "en" | "bn" | "zh") {
  await page
    .context()
    .addCookies([
      {
        name: "setu_lang",
        value: lang,
        url:
          page.url() === "about:blank" ? "http://localhost:3000" : page.url(),
      },
    ]);
}

test("renders the quick-start with QR codes and valid links", async ({
  page,
  baseURL,
}) => {
  await page.goto("/judges");
  await expect(
    page.getByRole("heading", { level: 1, name: "Judge quick-start" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open the live demo" }),
  ).toHaveAttribute("href", "/demo");
  await expect(
    page.getByRole("button", { name: "Create my sandbox" }),
  ).toBeVisible();

  const qrDemo = page.getByTestId("qr-demo");
  await expect(qrDemo.locator("svg")).toBeVisible();
  await expect(qrDemo).toHaveAttribute(
    "aria-label",
    new RegExp(`${baseURL}/demo`),
  );
  await expect(page.getByTestId("qr-judges").locator("svg")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /Download SVG of the QR code for Live demo/,
    }),
  ).toBeEnabled();

  const hrefs = await page
    .locator("main a[href]")
    .evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
  expect(hrefs.length).toBeGreaterThan(20);
  for (const h of hrefs) {
    expect(h, "no empty or placeholder hrefs").not.toMatch(
      /^(#?|undefined|null|javascript:.*)$/,
    );
  }
  // Internal links resolve (skip signed-in app screens, they redirect when logged out).
  for (const h of new Set(
    hrefs.filter((x) => x.startsWith("/") && !x.startsWith("/app")),
  )) {
    const res = await page.request.get(h.split("#")[0] || "/");
    expect(res.status(), h).toBeLessThan(400);
  }
  // Unset external links are labelled, not dead.
  await expect(page.getByTestId("resource-video")).toContainText(
    /Link coming|Demo video/,
  );
});

test("download SVG produces a file", async ({ page }) => {
  await page.goto("/judges");
  await expect(page.getByTestId("qr-demo").locator("svg")).toBeVisible();
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page
      .getByRole("button", {
        name: /Download SVG of the QR code for Live demo/,
      })
      .click(),
  ]);
  expect(dl.suggestedFilename()).toBe("setu-demo-qr.svg");
});

for (const lang of ["en", "bn"] as const) {
  test(`axe: no serious or critical violations (${lang})`, async ({ page }) => {
    await page.goto("/");
    await setLang(page, lang);
    await page.goto("/judges");
    await expect(page.locator("html")).toHaveAttribute("lang", lang);
    await expect(page.getByTestId("qr-demo").locator("svg")).toBeVisible();
    const res = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    const bad = res.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(
      bad.map(
        (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
      ),
    ).toEqual([]);
  });
}

test("360 px: no horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto("/judges");
  await expect(page.getByTestId("qr-demo").locator("svg")).toBeVisible();
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});
