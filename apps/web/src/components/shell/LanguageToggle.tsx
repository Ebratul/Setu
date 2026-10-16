"use client";

import { useLang, useT } from "@/i18n";
import { SegmentedControl } from "@/components/ui/SegmentedControl";

export function LanguageToggle() {
  const { lang, setLang } = useLang();
  const t = useT();
  return (
    <SegmentedControl
      legend={t("lang.label")}
      value={lang}
      onChange={setLang}
      options={[
        { value: "en", label: t("lang.en"), title: "English" },
        { value: "bn", label: t("lang.bn"), title: "বাংলা" },
      ]}
    />
  );
}
