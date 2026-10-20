// Shared constants for the P30 e2e stack (config, helpers and specs import this).
export const MOCK_PORT = 4010;
export const MOCK_ORIGIN = `http://127.0.0.1:${MOCK_PORT}`;
export const MOCK_AUTH_BASE = `${MOCK_ORIGIN}/neondb/auth`;

/** Local-only database; the P30 config recreates it on every run. */
export const E2E_DB_NAME = "setu_e2e_p30";
export const ADMIN_DB_URL = "postgresql://setu:setu@localhost:5435/postgres";
export const E2E_DB_URL = `postgresql://setu:setu@localhost:5435/${E2E_DB_NAME}`;

/** A: DEMO_MODE=true, demo cookie off (the main backend). B: DEMO_MODE=false. C: DEMO_MODE=true + DEMO_COOKIE_IN_NEON. */
export const AGENTS = {
  A: { port: 8010, url: "http://127.0.0.1:8010" },
  B: { port: 8011, url: "http://127.0.0.1:8011" },
  C: { port: 8012, url: "http://127.0.0.1:8012" },
} as const;
export type AgentKey = keyof typeof AGENTS;

export const ADMIN_EMAIL = "p30-admin@setu-e2e.test";
export const JUDGE_CODE = "e2e-judge-invite-code-0001";
// Throwaway Fernet key, only ever used by the e2e backends.
export const FIELD_KEY = "q9lOZt0Y3oYb1VQd2s0m6m3wYtZ4m2kq4d0yLk0w1gA=";
