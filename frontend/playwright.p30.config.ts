import { execFileSync } from "node:child_process";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

import {
  ADMIN_DB_URL,
  ADMIN_EMAIL,
  AGENTS,
  E2E_DB_NAME,
  E2E_DB_URL,
  FIELD_KEY,
  JUDGE_CODE,
  MOCK_AUTH_BASE,
  MOCK_PORT,
  type AgentKey,
} from "./e2e/p30/env";

// Run: pnpm --dir frontend exec playwright test -c playwright.p30.config.ts
// Stack (all local; the hosted database is never touched):
//   mock Neon Auth :4010, three FastAPI backends :8010/:8011/:8012 on one throwaway local Postgres DB,
//   and the web app on :3000 (an already running `next dev` is reused, its /api calls are re-routed
//   to the right backend by e2e/p30/helpers.ts#useBackend).
const backend = path.resolve(__dirname, "../backend");

// Fresh database before any server starts (config runs in the runner first, workers skip it).
if (!process.env.P30_DB_READY) {
  const run = (cmd: string, args: string[], env: Record<string, string> = {}) =>
    execFileSync(cmd, args, { stdio: "pipe", env: { ...process.env, ...env } });
  run("psql", [ADMIN_DB_URL, "-qc", `DROP DATABASE IF EXISTS ${E2E_DB_NAME} WITH (FORCE)`]);
  run("psql", [ADMIN_DB_URL, "-qc", `CREATE DATABASE ${E2E_DB_NAME}`]);
  const dbEnv = { DATABASE_URL: E2E_DB_URL, APP_ENV: "dev" };
  run("uv", ["run", "--directory", backend, "alembic", "upgrade", "head"], dbEnv);
  run("uv", ["run", "--directory", backend, "python", "-m", "seed.cli", "seed"], dbEnv);
  process.env.P30_DB_READY = "1";
}
process.env.P30_E2E = "1";

function agent(key: AgentKey, extra: Record<string, string>) {
  const { port } = AGENTS[key];
  return {
    command: `uv run --directory ${backend} uvicorn app.main:app --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      APP_ENV: "dev",
      DATABASE_URL: E2E_DB_URL,
      AUTH_MODE: "neon",
      NEON_AUTH_BASE_URL: MOCK_AUTH_BASE,
      FIELD_ENCRYPTION_KEY: FIELD_KEY,
      ADMIN_EMAIL_ALLOWLIST: ADMIN_EMAIL,
      JUDGE_INVITE_CODES: JUDGE_CODE,
      DEMO_SESSION_SECRET: "e2e-only-demo-session-secret-0000000000",
      DEMO_COOKIE_IN_NEON: "false",
      RATE_LIMIT_ENABLED: "false",
      SMS_PROVIDER: "console",
      MAIL_PROVIDER: "console",
      ONBOARDING_AUTO_APPROVE: "false",
      ...extra,
    },
  };
}

export default defineConfig({
  testDir: "e2e",
  globalSetup: "./e2e/p30/global-setup.ts",
  testMatch: /p30-.*\.spec\.ts$/,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure", actionTimeout: 15_000 },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/p30/mock-neon-auth.mjs",
      url: `http://127.0.0.1:${MOCK_PORT}/__test/health`,
      reuseExistingServer: false,
      env: { MOCK_NEON_PORT: String(MOCK_PORT) },
    },
    agent("A", { DEMO_MODE: "true" }),
    agent("B", { DEMO_MODE: "false" }),
    agent("C", { DEMO_MODE: "true", DEMO_COOKIE_IN_NEON: "true" }),
    {
      command: "pnpm dev",
      url: process.env.E2E_BASE_URL ?? "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 180_000,
      env: { AGENT_URL: AGENTS.A.url },
    },
  ],
});
