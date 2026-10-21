import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

// Browser half of the production smoke. Point E2E_BASE_URL at the deployed (or local) site.
// The agent must run with DEMO_MODE=true (replay) so the guided demo is deterministic.
// One shared browser context (so the sandbox cookie carries over); each step is its own test so a failure does not hide the rest.
test.setTimeout(420_000);
let page: Page;
test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext()).newPage();
});
test.afterAll(async () => {
  await page.context().close();
});

const timings: { name: string; ms: number }[] = [];
async function timed<T>(name: string, fn: () => Promise<T>): Promise<T> {
  return test.step(name, async () => {
    const t0 = Date.now();
    try {
      return await fn();
    } finally {
      timings.push({ name, ms: Date.now() - t0 });
    }
  });
}

test.afterAll(() => {
  const w = Math.max(...timings.map((t) => t.name.length), 4);
  console.log(
    `\nSMOKE TIMINGS (${process.env.E2E_BASE_URL ?? "http://localhost:3000"})`,
  );
  for (const t of timings)
    console.log(`  ${t.name.padEnd(w)}  ${(t.ms / 1000).toFixed(2)} s`);
});

const FIX = path.resolve(__dirname, "fixtures/audit");

async function judgeLogin(page: Page) {
  await page.goto("/login");
  await page
    .getByRole("button", { name: /Demo Judge/ })
    .first()
    .click();
  await page.waitForURL(/\/app/);
}

test("landing loads", async () => {
  await timed("landing loads", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("system-status").first()).toBeVisible();
  });
});

test("/judges loads with QR", async () => {
  await timed("/judges loads with QR", async () => {
    await page.goto("/judges");
    await expect(
      page.getByRole("heading", { level: 1, name: "Judge quick-start" }),
    ).toBeVisible();
    await expect(page.getByTestId("qr-demo").locator("svg")).toBeVisible();
    await expect(page.getByTestId("system-status").first()).toHaveAttribute(
      "data-level",
      /^(ok|degraded)$/,
      { timeout: 20_000 },
    );
  });
});

test("judge mode creates a sandbox and opens /demo", async () => {
  await timed("judge mode creates a sandbox and opens /demo", async () => {
    await page.goto("/judges");
    await page.getByRole("button", { name: "Create my sandbox" }).click();
    const failed = page
      .getByRole("alert")
      .filter({ hasText: /Could not start/ });
    await Promise.race([
      page.waitForURL(/\/demo\?judge=1/),
      failed.waitFor().then(() => {
        throw new Error(
          "Judge mode could not create a sandbox (rate limit or capacity?)",
        );
      }),
    ]);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const run = await page.request.get("/api/demo/run");
    expect(run.ok()).toBe(true);
    expect((await run.json()).sandbox?.id).toBeTruthy();
  });
});

test("guided demo auto-plays all steps", async () => {
  await timed("guided demo auto-plays all steps", async () => {
    await page.goto("/demo/run?play=1");
    await expect(page.getByTestId("sim-banner")).toBeVisible();
    await expect(page.getByTestId("score-count")).toHaveText("17 of 17", {
      timeout: 300_000,
    });
    await expect(page.getByTestId("scene-failed")).toHaveCount(0);
  });
});

test("attack console blocks hidden-text attack", async () => {
  await timed("attack console blocks hidden-text attack", async () => {
    await judgeLogin(page);
    await page.goto("/demo/attack-console");
    await page
      .getByRole("button", { name: /Hidden white text/ })
      .first()
      .click();
    await expect(
      page.getByRole("switch", { name: /Defences/ }),
    ).toHaveAttribute("aria-checked", "true");
    await page.getByRole("button", { name: "Run attack" }).click();
    await expect(page.getByTestId("result-text")).toContainText(
      "Attack blocked",
      { timeout: 30_000 },
    );
  });
});

test("/verify validates the exported log", async () => {
  await timed("/verify validates the exported log", async () => {
    await page.goto("/verify");
    await page.getByText("Advanced: use another public key (PEM)").click();
    await page
      .getByLabel("Public key file (.pem)")
      .setInputFiles(path.join(FIX, "test-public-key.pem"));
    await page
      .getByLabel("Operation log (.jsonl)")
      .setInputFiles(path.join(FIX, "good.jsonl"));
    await expect(page.getByTestId("log-result")).toContainText(
      "Verified ✓ 12 entries",
    );
  });
});

test("privacy playground masks a sample", async () => {
  await timed("privacy playground masks a sample", async () => {
    await judgeLogin(page);
    await page.goto("/demo/privacy-playground");
    await expect(
      page.getByTestId("live-source").locator('mark[data-type="NID"]').first(),
    ).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Send to AI (dry run)" }).click();
    await expect(page.getByTestId("pane-masked")).toContainText("⟦NID_1⟧", {
      timeout: 20_000,
    });
  });
});

test("sandbox reset", async () => {
  await timed("sandbox reset", async () => {
    await page.goto("/demo/run");
    await page.getByRole("button", { name: "Reset demo" }).first().click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Reset demo" })
      .click();
    await expect
      .poll(
        async () =>
          (await (await page.request.get("/api/demo/run")).json()).passed,
        { timeout: 120_000 },
      )
      .toBe(0);
  });
});
