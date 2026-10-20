import type { ReactNode } from "react";
import { render } from "@testing-library/react";

import { I18nProvider } from "@/i18n";

export function setLang(lang: "en" | "bn" | "zh") {
  document.cookie = `setu_lang=${lang}; path=/`;
}

export const renderI18n = (ui: ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

export const user = (role: "BUYER" | "ADMIN" | "JUDGE" | "SUPPLIER") => ({
  id: `u-${role}`,
  email: "x@example.com",
  display_name: "Test",
  role,
  language: "en" as const,
  party_id: null,
  party_name: null,
});
