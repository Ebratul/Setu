"use client";

import { useLang, useT, type Lang } from "@/i18n";
import { SegmentedControl } from "@/components/ui/SegmentedControl";

type Props = { withZh?: boolean };

export function LanguageToggle({ withZh = false }: Props) {
  const { lang, setLang } = useLang();
  const t = useT();
  const options: { value: Lang; label: string; title: string }[] = [
    { value: "en", label: t("lang.en"), title: "English" },
    { value: "bn", label: t("lang.bn"), title: "বাংলা" },
  ];
  if (withZh) options.push({ value: "zh", label: t("lang.zh"), title: "中文" });
  const value: Lang = lang === "zh" && !withZh ? "en" : lang;
  return (
    <SegmentedControl
      legend={t("lang.label")}
      value={value}
      onChange={setLang}
      options={options}
    />
  );
}
