import { Badge, type Tone } from "@/components/ui/Badge";
import { useT } from "@/i18n";
import type { Recommendation } from "@/lib/api/onboarding";

const TONE: Record<Recommendation, Tone> = { AUTO_CLEAR: "success", NEEDS_REVIEW: "warning", BLOCK: "danger" };

export function RecommendationBadge({ value }: { value: Recommendation }) {
  const t = useT();
  return <Badge tone={TONE[value]}>{t(`adm.onb.rec.${value}`)}</Badge>;
}
