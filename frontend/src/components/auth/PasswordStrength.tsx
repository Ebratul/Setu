"use client";

import { Icon } from "@/components/ui/Icon";
import { useT } from "@/i18n";

export type Strength = "weak" | "fair" | "strong";

export function passwordStrength(pw: string): Strength {
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  if (pw.length >= 12 && classes >= 3) return "strong";
  if (pw.length >= 8 && classes >= 2) return "fair";
  return "weak";
}

const ICON = { weak: "warn", fair: "info", strong: "check" } as const;
const TONE = { weak: "text-danger", fair: "text-ink", strong: "text-success" } as const;

type Props = { id: string; password: string };

/** Advisory only; the identity provider enforces the real password policy. */
export function PasswordStrength({ id, password }: Props) {
  const t = useT();
  const level = passwordStrength(password);
  return (
    <div id={id} aria-live="polite" className="mt-1 text-xs">
      {password ? (
        <p className={`flex items-center gap-1 font-medium ${TONE[level]}`}>
          <Icon name={ICON[level]} size={14} />
          {t("auth.strength.label", { level: t(`strength.${level}`) })}
        </p>
      ) : null}
      <p className="text-muted">{t("auth.strength.hint")}</p>
    </div>
  );
}
