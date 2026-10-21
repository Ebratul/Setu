"use client";

import { FormField, inputClass } from "@/components/ui/FormField";
import { hasKey, useT } from "@/i18n";
import { labelKey } from "@/lib/onboarding/errors";
import type { FieldDef, FieldError } from "@/lib/onboarding/validate";

type Props = {
  def: FieldDef;
  value: string;
  error?: FieldError;
  masked?: string | null;
  onChange: (value: string) => void;
};

export function Field({ def, value, error, masked, onChange }: Props) {
  const t = useT();
  const k = labelKey(def.key);
  const id = `ob-${k}`;
  const label = `${t(`ob.f.${k}`)}${def.required ? " *" : ` (${t("ob.optional")})`}`;
  const hint = masked
    ? t("ob.savedMasked", { value: masked })
    : hasKey(`ob.h.${k}`)
      ? t(`ob.h.${k}`)
      : undefined;
  return (
    <FormField
      id={id}
      label={label}
      error={error ? t(error.key, error.vars) : null}
      hint={hint}
    >
      {(aria) =>
        def.kind === "select" ? (
          <select
            {...aria}
            aria-required={def.required}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className={`${inputClass} min-h-11`}
          >
            <option value="">{t("ob.choose")}</option>
            {def.options?.map((o) => (
              <option key={o} value={o}>
                {hasKey(`ob.o.${k}.${o}`) ? t(`ob.o.${k}.${o}`) : o}
              </option>
            ))}
          </select>
        ) : def.kind === "textarea" ? (
          <textarea
            {...aria}
            aria-required={def.required}
            rows={3}
            maxLength={def.max}
            lang={def.zh ? "zh" : undefined}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className={inputClass}
          />
        ) : (
          <input
            {...aria}
            aria-required={def.required}
            type={def.kind === "date" ? "date" : "text"}
            inputMode={def.inputMode}
            autoComplete={def.autoComplete ?? "off"}
            maxLength={def.max}
            lang={def.zh ? "zh" : undefined}
            value={value}
            onChange={(e) =>
              onChange(
                def.upper ? e.target.value.toUpperCase() : e.target.value,
              )
            }
            className={`${inputClass} min-h-11`}
          />
        )
      }
    </FormField>
  );
}
