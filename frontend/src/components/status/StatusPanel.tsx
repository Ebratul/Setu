"use client";

import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";
import { healthLevel } from "@/lib/health";

import { SystemStatusChip } from "./SystemStatusChip";
import { VersionBadge } from "./VersionBadge";
import { useAgentHealth } from "./useAgentHealth";

type Item = {
  id: string;
  label: string;
  value: boolean | string | null;
  yes?: string;
  no?: string;
};

/** Full status table for /judges#status; the same health poll as the footer chip. */
export function StatusPanel() {
  const t = useT();
  const state = useAgentHealth();
  const h = state.kind === "ready" ? state.health : null;
  const level =
    state.kind === "ready"
      ? healthLevel(state.health)
      : state.kind === "unreachable"
        ? "unreachable"
        : null;

  const items: Item[] = h
    ? [
        {
          id: "db",
          label: t("status.panel.db"),
          value: h.db === null ? null : h.db === "ok",
          yes: "status.detail.ok",
          no: "status.detail.unavailable",
        },
        {
          id: "ready",
          label: t("status.panel.ready"),
          value: h.ready,
          yes: "status.detail.ready",
          no: "status.detail.notReady",
        },
        {
          id: "kb",
          label: t("status.panel.kb"),
          value: h.kbIndexed,
          yes: "status.detail.indexed",
          no: "status.detail.notIndexed",
        },
        {
          id: "audit",
          label: t("status.panel.audit"),
          value: h.auditKeyLoaded,
          yes: "status.detail.loaded",
          no: "status.detail.missing",
        },
        {
          id: "replay",
          label: t("status.panel.replay"),
          value: h.replayFixturesPresent,
          yes: "status.detail.present",
          no: "status.detail.missing",
        },
        {
          id: "demo",
          label: t("status.panel.demoMode"),
          value: h.demoMode,
          yes: "status.detail.on",
          no: "status.detail.off",
        },
        {
          id: "demoReplay",
          label: t("status.panel.demoReplay"),
          value: h.demoReplay,
          yes: "status.detail.on",
          no: "status.detail.off",
        },
      ]
    : [];

  return (
    <div className="grid gap-4" data-testid="status-panel">
      <div className="flex flex-wrap items-center gap-4">
        <SystemStatusChip state={state} />
        <VersionBadge state={state} />
      </div>
      {level === "unreachable" ? (
        <p className="text-sm text-muted">{t("status.panel.unreachable")}</p>
      ) : null}
      {items.length > 0 ? (
        <ul className="grid gap-2 sm:grid-cols-2">
          {items.map((i) => {
            const tone: Tone =
              i.value === null ? "neutral" : i.value ? "success" : "warning";
            const text =
              i.value === null
                ? t("status.detail.unknown")
                : t(i.value ? (i.yes ?? "") : (i.no ?? ""));
            return (
              <li
                key={i.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2 text-sm"
              >
                <span className="text-ink">{i.label}</span>
                <Badge tone={tone}>{text}</Badge>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
