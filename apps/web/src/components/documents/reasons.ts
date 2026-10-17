import type { Lang } from "@/i18n";
import type { FindingOut } from "@/lib/api/documents";

/** Neutral check title (never the problem statement). */
export const findingLabel = (f: FindingOut, lang: Lang) => (lang === "bn" ? f.label_bn : f.label_en);
