import { execFileSync } from "node:child_process";
import path from "node:path";

// The financing spec applies for a loan, which resolves the demo shortfall. Set E2E_RESET_DEMO=1
// (with DATABASE_URL pointing at the local demo DB) to start every run from the seeded state.
// seed.cli refuses to reset a non-local database.
export default function globalSetup() {
  if (process.env.E2E_RESET_DEMO !== "1") return;
  const agent = path.resolve(__dirname, "../../../services/agent");
  execFileSync("uv", ["run", "--directory", agent, "python", "-m", "seed.cli", "reset-demo"], {
    stdio: "inherit",
  });
}
