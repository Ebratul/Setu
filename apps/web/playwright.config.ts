import { defineConfig, devices } from "@playwright/test";

// Specs share one demo database and financing.spec mutates it, so run files serially
// (alphabetical: analysis, dashboard, financing). See e2e/global-setup.ts for E2E_RESET_DEMO.
export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/global-setup.ts",
  workers: 1,
  fullyParallel: false,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
