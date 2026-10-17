import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { deal, milestone } from "@/components/deals/fixtures";
import { I18nProvider } from "@/i18n";
import type { DocumentOut } from "@/lib/api/documents";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/documents", async (orig) => {
  const real = await orig<typeof import("@/lib/api/documents")>();
  return { ...real, listDocuments: vi.fn(), getDocument: vi.fn() };
});
import * as api from "@/lib/api/documents";

import { DocumentsTab } from "./DocumentsTab";

const row = (over: Partial<DocumentOut>): DocumentOut => ({
  id: "22222222-2222-4222-8222-222222222222",
  deal_id: "d",
  deal_reference: "SETU-2026-0001",
  milestone_id: null,
  milestone_seq: 2,
  doc_type: "BILL_OF_LADING",
  file_name: "bl.pdf",
  mime_type: "application/pdf",
  size_bytes: 1,
  sha256: null,
  status: "UPLOADED",
  check_status: "FAILED",
  score: 100,
  top_reason: { code: "HIDDEN_TEXT", status: "FAIL", label_en: "Hidden text", label_bn: "x", issue_en: "The document contains hidden text", issue_bn: "y" },
  instruction_from_document: true,
  hidden_text_found: true,
  uploaded_at: "2026-10-17T00:00:00Z",
  ...over,
});

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
});

describe("DocumentsTab", () => {
  it("lists documents with badge, score and top reason, plus the evidence checklist", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({
      documents: [row({}), row({ id: "33333333-3333-4333-8333-333333333333", doc_type: "PACKING_LIST", check_status: "PASSED", score: 0 })],
    });
    render(
      <I18nProvider>
        <DocumentsTab
          deal={deal({
            viewer_role: "BUYER",
            milestones: [milestone({ required_evidence: [{ doc_type: "PACKING_LIST", status: "VERIFIED", documents: 1 }, { doc_type: "BILL_OF_LADING", status: "REJECTED", documents: 1 }] })],
          })}
          onChanged={vi.fn()}
        />
      </I18nProvider>,
    );
    const rows = await screen.findAllByTestId("doc-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByTestId("doc-status")).toHaveTextContent("Failed");
    expect(within(rows[0]).getByTestId("doc-score")).toHaveTextContent("100");
    await waitFor(() => expect(within(rows[0]).getByTestId("doc-top-reason")).toHaveTextContent("The document contains hidden text"));
    expect(within(rows[0]).getByRole("link", { name: /Open/ })).toHaveAttribute("href", "/app/documents/22222222-2222-4222-8222-222222222222");
    expect(api.getDocument).not.toHaveBeenCalled();
    const ev = screen.getAllByRole("listitem").filter((li) => li.hasAttribute("data-status") && li.closest("[data-testid=evidence-list]"));
    expect(ev.map((e) => e.dataset.status)).toEqual(["VERIFIED", "REJECTED"]);
    expect(screen.getByTestId("dropzone")).toBeInTheDocument();
  });

  it("shows no score when the API returns null and no upload for a judge", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue({ documents: [row({ score: null, check_status: "PENDING", top_reason: null })] });
    render(
      <I18nProvider>
        <DocumentsTab deal={deal({ viewer_role: "JUDGE" })} onChanged={vi.fn()} />
      </I18nProvider>,
    );
    const r = await screen.findByTestId("doc-row");
    expect(within(r).getByTestId("doc-status")).toHaveTextContent("Checking");
    expect(within(r).queryByTestId("doc-score")).toBeNull();
    expect(screen.queryByTestId("dropzone")).toBeNull();
  });
});
