import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { DocumentOut } from "@/lib/api/documents";

vi.mock("@/lib/api/documents", async (orig) => {
  const real = await orig<typeof import("@/lib/api/documents")>();
  return { ...real, listDocuments: vi.fn() };
});
vi.mock("@/lib/api/registry", async (orig) => {
  const real = await orig<typeof import("@/lib/api/registry")>();
  return { ...real, lenderCheck: vi.fn() };
});
import * as docs from "@/lib/api/documents";
import * as reg from "@/lib/api/registry";

import { deal } from "./fixtures";
import { LenderCheckDemo } from "./LenderCheckDemo";

const wrap = (role: "BUYER" | "JUDGE" | "ADMIN") =>
  render(
    <I18nProvider>
      <LenderCheckDemo deal={deal({ viewer_role: role })} />
    </I18nProvider>,
  );
const row = (id: string, doc_type: string) => ({ id, doc_type }) as unknown as DocumentOut;

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

describe("LenderCheckDemo", () => {
  it("is hidden for a buyer", () => {
    wrap("BUYER");
    expect(screen.queryByTestId("lender-check-demo")).toBeNull();
  });

  it("is visible for a buyer when NEXT_PUBLIC_DEMO_MODE=1", () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "1");
    wrap("BUYER");
    expect(screen.getByRole("button", { name: "Try to finance this invoice at Lender B" })).toBeInTheDocument();
  });

  it("judge: checks the proforma first and shows the blocked explanation", async () => {
    vi.mocked(docs.listDocuments).mockResolvedValue({
      documents: [row("ci", "COMMERCIAL_INVOICE"), row("pi", "PROFORMA_INVOICE")],
    } as never);
    vi.mocked(reg.lenderCheck).mockResolvedValue({
      simulated: true,
      result: "EXACT_DUPLICATE",
      already_registered_for: "FINANCING_COLLATERAL",
      registered_on: "2026-10-01",
      held_by: "Lender A",
    });
    wrap("JUDGE");
    fireEvent.click(screen.getByRole("button", { name: /Try to finance/ }));
    const blocked = await screen.findByTestId("lender-check-blocked");
    expect(reg.lenderCheck).toHaveBeenCalledWith("setu-partner-finance", "pi");
    expect(blocked).toHaveTextContent(
      "Lender B would reject this: the invoice is already registered as financing collateral (held by Lender A) since Oct 1, 2026.",
    );
    expect(screen.getAllByText("Simulated").length).toBeGreaterThan(0);
  });

  it("shows no conflict for a new invoice and disables the button while loading", async () => {
    vi.mocked(docs.listDocuments).mockResolvedValue({ documents: [row("ci", "COMMERCIAL_INVOICE")] } as never);
    vi.mocked(reg.lenderCheck).mockResolvedValue({ simulated: true, result: "NEW" });
    wrap("ADMIN");
    fireEvent.click(screen.getByRole("button", { name: /Try to finance/ }));
    expect(screen.getByRole("button", { name: /Checking/ })).toBeDisabled();
    await waitFor(() => expect(screen.getByTestId("lender-check-clear")).toHaveTextContent("No conflict found"));
    expect(reg.lenderCheck).toHaveBeenCalledWith("setu-partner-finance", "ci");
  });

  it("explains when the deal has no invoice", async () => {
    vi.mocked(docs.listDocuments).mockResolvedValue({ documents: [] } as never);
    wrap("JUDGE");
    fireEvent.click(screen.getByRole("button", { name: /Try to finance/ }));
    expect(await screen.findByText(/no invoice document/)).toBeInTheDocument();
    expect(reg.lenderCheck).not.toHaveBeenCalled();
  });
});
