"use client";

import { useT } from "@/i18n";
import {
  formatBuildTime,
  shortSha,
  webBuild,
  type AgentHealth,
} from "@/lib/health";

import type { HealthState } from "./useAgentHealth";

type Props = { state: HealthState };

/** Shows exactly which web build and agent build a judge is looking at. Web falls back to "dev". */
export function VersionBadge({ state }: Props) {
  const t = useT();
  const web = webBuild();
  const h: AgentHealth | null = state.kind === "ready" ? state.health : null;

  const webText = [web.sha, formatBuildTime(web.builtAt)]
    .filter(Boolean)
    .join(" · ");
  const agentParts = h
    ? [
        h.version ? `v${h.version}` : null,
        shortSha(h.gitSha),
        formatBuildTime(h.builtAt),
      ].filter(Boolean)
    : [];
  const agentText =
    state.kind === "loading"
      ? t("status.version.loading")
      : agentParts.length > 0
        ? agentParts.join(" · ")
        : t("status.version.unavailable");

  return (
    <p className="font-mono text-xs text-muted" data-testid="version-badge">
      <span>
        {t("status.version.web")}{" "}
        <span data-testid="version-web">{webText}</span>
      </span>
      <span aria-hidden="true"> | </span>
      <span>
        {t("status.version.agent")}{" "}
        <span data-testid="version-agent">{agentText}</span>
      </span>
    </p>
  );
}
