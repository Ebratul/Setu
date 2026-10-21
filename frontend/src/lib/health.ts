/** Defensive parsing of the agent's /health payload: every field beyond `status`/`db`/`version` may be absent. */

export type AgentHealth = {
  status: string | null;
  db: string | null;
  version: string | null;
  gitSha: string | null;
  builtAt: string | null;
  ready: boolean | null;
  kbIndexed: boolean | null;
  auditKeyLoaded: boolean | null;
  replayFixturesPresent: boolean | null;
  demoMode: boolean | null;
  demoReplay: boolean | null;
};

export type HealthLevel = "ok" | "degraded" | "unreachable";

const str = (v: unknown): string | null =>
  typeof v === "string" && v.trim() !== "" ? v : null;
const bool = (v: unknown): boolean | null =>
  typeof v === "boolean" ? v : null;

export function parseHealth(raw: unknown): AgentHealth {
  const o =
    raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  return {
    status: str(o.status),
    db: str(o.db),
    version: str(o.version),
    gitSha: str(o.git_sha),
    builtAt: str(o.built_at),
    ready: bool(o.ready),
    kbIndexed: bool(o.kb_indexed),
    auditKeyLoaded: bool(o.audit_key_loaded),
    replayFixturesPresent: bool(o.replay_fixtures_present),
    demoMode: bool(o.demo_mode),
    demoReplay: bool(o.demo_replay),
  };
}

/** `ok` only when the agent says so and nothing it reports is failing. */
export function healthLevel(h: AgentHealth | null): HealthLevel {
  if (!h) return "unreachable";
  const failing =
    (h.status !== null && h.status !== "ok") ||
    (h.db !== null && h.db !== "ok") ||
    h.ready === false ||
    h.kbIndexed === false ||
    h.auditKeyLoaded === false ||
    h.replayFixturesPresent === false;
  return failing ? "degraded" : "ok";
}

export const shortSha = (sha: string | null): string | null =>
  sha ? sha.slice(0, 7) : null;

export type WebBuild = { sha: string; builtAt: string | null };

/** NEXT_PUBLIC_* must be read as literal `process.env.X` so Next inlines them at build time. */
export function webBuild(): WebBuild {
  const sha = process.env.NEXT_PUBLIC_GIT_SHA?.trim();
  const built = process.env.NEXT_PUBLIC_BUILD_TIME?.trim();
  return { sha: sha ? sha.slice(0, 7) : "dev", builtAt: built ? built : null };
}

/** Short, locale-free UTC date-time ("2026-10-20 14:03 UTC"); returns the raw string if it is not a date. */
export function formatBuildTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
