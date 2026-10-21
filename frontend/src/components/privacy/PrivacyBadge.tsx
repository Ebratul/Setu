"use client";

import { Badge } from "@/components/ui/Badge";
import { useLang, useT } from "@/i18n";

import { fmtNum } from "./privacyText";

type Props =
  | { kind: "leaked"; count: number }
  | { kind: "protected"; count: number }
  | { kind: "notSent" };

export function PrivacyBadge(props: Props) {
  const t = useT();
  const { lang } = useLang();
  if (props.kind === "notSent") {
    return (
      <span title={t("privacy.notSentHint")} data-testid="not-sent-badge">
        <Badge tone="info" icon="◌">
          {t("privacy.notSent")}
        </Badge>
      </span>
    );
  }
  if (props.kind === "protected") {
    return (
      <span data-testid="protected-badge">
        <Badge tone="success" icon="🛡">
          {t("privacy.protectedBadge", { n: fmtNum(props.count, lang) })}
        </Badge>
      </span>
    );
  }
  const ok = props.count === 0;
  return (
    <span data-testid="leaked-badge" data-leaked={props.count} title={ok ? t("privacy.leakedOk") : undefined}>
      <Badge tone={ok ? "success" : "danger"} icon={ok ? "✓" : "⚠"}>
        {t("privacy.leaked", { n: fmtNum(props.count, lang) })}
      </Badge>
    </span>
  );
}
