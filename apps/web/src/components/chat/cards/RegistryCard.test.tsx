import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";
import type { ChatCardData } from "@/lib/api/chat";

import { ChatCard } from "./ChatCard";

const card = (data: Record<string, unknown>) =>
  ({
    explanation_codes: [],
    explanation_en: "Registry explanation.",
    explanation_bn: "রেজিস্ট্রি ব্যাখ্যা।",
    simulated: true,
    card_type: "registry",
    data: {
      document_id: "22222222-2222-4222-8222-222222222222",
      doc_type: "PROFORMA_INVOICE",
      doc_label_en: "Proforma invoice",
      doc_label_bn: "প্রোফর্মা ইনভয়েস",
      deal_ref: "SETU-2026-0001",
      state: "NOT_REGISTERED",
      result: "NEW",
      purpose: null,
      holder: null,
      registered_on: null,
      route: "/app/documents/22222222-2222-4222-8222-222222222222",
      ...data,
    },
  }) as unknown as ChatCardData;

const show = (c: ChatCardData) =>
  render(
    <I18nProvider>
      <ChatCard card={c} />
    </I18nProvider>,
  );

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

describe("RegistryCard", () => {
  it("duplicate: red badge, holder and date, link to the document", () => {
    show(card({ state: "DUPLICATE", result: "EXACT_DUPLICATE", purpose: "FINANCING_COLLATERAL", holder: "Lender A", registered_on: "2026-10-01" }));
    expect(screen.getByTestId("registry-card-state")).toHaveTextContent("Duplicate");
    expect(screen.getByTestId("registry-card-line")).toHaveTextContent("Financing collateral with Lender A on Oct 1, 2026");
    expect(screen.getByRole("link", { name: /Open document/ })).toHaveAttribute("href", "/app/documents/22222222-2222-4222-8222-222222222222");
    expect(screen.getByText("Simulated data")).toBeInTheDocument();
  });

  it("not registered: neutral text", () => {
    show(card({}));
    expect(screen.getByTestId("registry-card-line")).toHaveTextContent("Not registered yet");
  });
});
