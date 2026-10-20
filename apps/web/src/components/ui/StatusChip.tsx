import type { ReactNode } from "react";

import { Badge, type Tone } from "./Badge";

const MAP: Record<string, Tone> = {
  OK: "success",
  PASSED: "success",
  COMPLETED: "success",
  RELEASED: "success",
  ACTIVE: "success",
  PENDING: "warning",
  PENDING_APPROVAL: "warning",
  REVIEW: "warning",
  WARNING: "warning",
  FAILED: "danger",
  BLOCKED: "danger",
  REJECTED: "danger",
  FRAUD: "danger",
  INFO: "info",
  FUNDED: "info",
  IN_PROGRESS: "info",
};

type Props = { status: string; label?: ReactNode };

/** Maps a backend status code to tone + icon + text; unknown codes render neutral. */
export function StatusChip({ status, label }: Props) {
  return <Badge tone={MAP[status.toUpperCase()] ?? "neutral"}>{label ?? status.replaceAll("_", " ")}</Badge>;
}
