import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";

const TONE: Record<"PASS" | "WARN" | "FAIL", Tone> = { PASS: "success", WARN: "warning", FAIL: "danger" };

/** Check outcome as icon + text + colour. */
export function CheckStatusBadge({ status }: { status: "PASS" | "WARN" | "FAIL" }) {
  const t = useT();
  return <Badge tone={TONE[status]}>{t(`onb.checkStatus.${status}`)}</Badge>;
}
