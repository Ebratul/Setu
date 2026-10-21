"use client";

import Link from "next/link";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Tooltip } from "@/components/ui/Tooltip";
import { useT } from "@/i18n";
import { healthLevel, type AgentHealth, type HealthLevel } from "@/lib/health";

import type { HealthState } from "./useAgentHealth";

const TONE: Record<HealthLevel, Tone> = {
  ok: "success",
  degraded: "warning",
  unreachable: "danger",
};

export const STATUS_URL = process.env.NEXT_PUBLIC_STATUS_URL?.trim() || null;

function flag(
  t: ReturnType<typeof useT>,
  v: boolean | null,
  yes: string,
  no: string,
) {
  return v === null ? t("status.detail.unknown") : v ? t(yes) : t(no);
}

export function healthDetail(
  t: ReturnType<typeof useT>,
  h: AgentHealth | null,
): string {
  if (!h) return t("status.detail.unreachable");
  return [
    t("status.detail.db", { v: h.db ?? t("status.detail.unknown") }),
    t("status.detail.kb", {
      v: flag(
        t,
        h.kbIndexed,
        "status.detail.indexed",
        "status.detail.notIndexed",
      ),
    }),
    t("status.detail.audit", {
      v: flag(
        t,
        h.auditKeyLoaded,
        "status.detail.loaded",
        "status.detail.missing",
      ),
    }),
    t("status.detail.replay", {
      v: flag(
        t,
        h.replayFixturesPresent,
        "status.detail.present",
        "status.detail.missing",
      ),
    }),
  ].join(" · ");
}

type Props = { state: HealthState };

/** Footer chip: icon + text (never colour only), links to the status page or /judges#status. */
export function SystemStatusChip({ state }: Props) {
  const t = useT();
  const level: HealthLevel | "checking" =
    state.kind === "loading"
      ? "checking"
      : state.kind === "unreachable"
        ? "unreachable"
        : healthLevel(state.health);
  const health = state.kind === "ready" ? state.health : null;
  const label = t(`status.chip.${level}`);
  const className =
    "inline-flex min-h-11 items-center gap-2 rounded-lg focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:outline-none";
  const inner = (
    <>
      <span className="text-muted">{t("status.chip.label")}</span>
      <Badge tone={level === "checking" ? "neutral" : TONE[level]}>
        {label}
      </Badge>
    </>
  );
  return (
    <span
      className="inline-flex items-center gap-1"
      data-testid="system-status"
      data-level={level}
      role="status"
    >
      {STATUS_URL ? (
        <a
          href={STATUS_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={className}
        >
          {inner}
          <span className="sr-only">{t("status.chip.newTab")}</span>
        </a>
      ) : (
        <Link href="/judges#status" className={className}>
          {inner}
        </Link>
      )}
      {level === "checking" ? null : (
        <Tooltip label={healthDetail(t, health)} />
      )}
    </span>
  );
}
