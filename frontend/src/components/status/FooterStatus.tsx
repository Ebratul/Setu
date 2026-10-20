"use client";

import { SystemStatusChip } from "./SystemStatusChip";
import { VersionBadge } from "./VersionBadge";
import { useAgentHealth } from "./useAgentHealth";

/** One health poll feeds both the chip and the version badge. */
export function FooterStatus() {
  const state = useAgentHealth();
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
      <SystemStatusChip state={state} />
      <VersionBadge state={state} />
    </div>
  );
}
