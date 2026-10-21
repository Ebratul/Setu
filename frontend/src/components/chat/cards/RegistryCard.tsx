"use client";

import { useLang, useT } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";
import { formatDate } from "@/lib/format";
import { Badge, type Tone } from "@/components/ui/Badge";

import { CardShell } from "./CardShell";

type Card = Extract<ChatCardData, { card_type: "registry" }>;

const META: Record<Card["data"]["state"], { tone: Tone; icon: string }> = {
  REGISTERED: { tone: "success", icon: "✓" },
  DUPLICATE: { tone: "danger", icon: "✕" },
  NOT_REGISTERED: { tone: "neutral", icon: "○" },
};

/** Compact, read-only registry status of one document. */
export function RegistryCard({ card }: { card: Card }) {
  const t = useT();
  const { lang } = useLang();
  const d = card.data;
  const m = META[d.state] ?? META.NOT_REGISTERED;
  const date = d.registered_on ? formatDate(d.registered_on.slice(0, 10), lang) : "";
  const purpose = d.purpose ? t(`reg.purpose.${d.purpose}`) : "";
  const line =
    d.state === "DUPLICATE"
      ? d.holder
        ? t("reg.card.dup", { purpose, holder: d.holder, date })
        : t("reg.card.dupNoHolder", { purpose, date })
      : d.state === "REGISTERED"
        ? t("reg.card.reg", { purpose, date })
        : t("reg.card.none");
  return (
    <CardShell
      type="registry"
      title={t("chat.card.registry", { ref: d.deal_ref })}
      explanationEn={card.explanation_en}
      explanationBn={card.explanation_bn}
      linkHref={d.route}
      linkLabel={t("chat.card.openDocument")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span data-testid="registry-card-state">
          <Badge tone={m.tone} icon={m.icon}>
            {t(`reg.state.${d.state}`)}
          </Badge>
        </span>
        <span className="text-sm text-ink" data-testid="registry-card-line">
          {line}
        </span>
      </div>
    </CardShell>
  );
}
