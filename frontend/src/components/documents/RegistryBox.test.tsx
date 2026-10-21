import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { DocumentDetail } from "@/lib/api/documents";
import type { DocumentRegistry } from "@/lib/api/registry";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/documents", async (orig) => {
  const real = await orig<typeof import("@/lib/api/documents")>();
  return { ...real, getDocument: vi.fn(), getHiddenText: vi.fn(), listDocuments: vi.fn(), recheckDocument: vi.fn(), acceptReference: vi.fn() };
});
vi.mock("@/lib/api/registry", async (orig) => {
  const real = await orig<typeof import("@/lib/api/registry")>();
  return { ...real, getDocumentRegistry: vi.fn() };
});
import * as docs from "@/lib/api/documents";
import * as reg from "@/lib/api/registry";

import { DocumentViewerPage } from "./DocumentViewerPage";
import { RegistryBox } from "./RegistryBox";

const ID = "22222222-2222-4222-8222-222222222222";
const wrap = (ui: React.ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);
const base: DocumentRegistry = { document_id: ID, state: "NOT_REGISTERED", result: "NEW" };

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
});

describe("RegistryBox", () => {
  it("REGISTERED: shows the date and purpose", () => {
    wrap(<RegistryBox registry={{ ...base, state: "REGISTERED", purpose: "ESCROW_EVIDENCE", registered_on: "2026-10-01" }} />);
    expect(screen.getByTestId("registry-box")).toHaveTextContent("Registered on Oct 1, 2026 as escrow evidence");
  });

  it("REGISTERED with a lender mentions the lender", () => {
    wrap(<RegistryBox registry={{ ...base, state: "REGISTERED", purpose: "FINANCING_COLLATERAL", registered_on: "2026-10-01", lender_name: "Lender A" }} />);
    expect(screen.getByTestId("registry-box")).toHaveTextContent("as financing collateral with Lender A");
  });

  it("DUPLICATE: red wording differs for exact and near copies", () => {
    const dup = { ...base, state: "DUPLICATE" as const, purpose: "FINANCING_COLLATERAL" as const, registered_on: "2026-10-01", lender_name: "Lender A" };
    const { unmount } = wrap(<RegistryBox registry={{ ...dup, result: "EXACT_DUPLICATE" }} />);
    expect(screen.getByTestId("registry-box")).toHaveTextContent(
      "Duplicate: exact copy of a document already registered as financing collateral with Lender A on Oct 1, 2026",
    );
    expect(screen.getByTestId("registry-box").className).toContain("border-danger");
    unmount();
    wrap(<RegistryBox registry={{ ...dup, result: "NEAR_DUPLICATE" }} />);
    expect(screen.getByTestId("registry-box")).toHaveTextContent("near copy (re-saved)");
  });

  it("NOT_REGISTERED: neutral text", () => {
    wrap(<RegistryBox registry={base} />);
    expect(screen.getByTestId("registry-box")).toHaveTextContent("Not registered yet");
  });
});

describe("registry box in the viewer", () => {
  const doc = {
    id: ID, deal_id: "d", deal_reference: "SETU-2026-0001", milestone_id: null, milestone_seq: 1,
    doc_type: "PROFORMA_INVOICE", file_name: "pi.pdf", mime_type: "application/pdf", size_bytes: 1, sha256: null,
    status: "UPLOADED", check_status: "PASSED", score: 0, instruction_from_document: false, hidden_text_found: false,
    uploaded_at: "2026-10-17T00:00:00Z", fields: null, findings: [], verdict: null, hidden_spans_count: 0, warnings: [],
    extractor_version: "f", file_url: null, file_inline_url: null, file_url_expires_at: null, simulated: true,
  } as unknown as DocumentDetail;

  it("buyer sees it; a 403 hides it silently", async () => {
    vi.mocked(docs.getDocument).mockResolvedValue({ ...doc, viewer_role: "BUYER" });
    vi.mocked(reg.getDocumentRegistry).mockResolvedValue({ ...base, state: "REGISTERED", purpose: "ESCROW_EVIDENCE", registered_on: "2026-10-01" });
    const { unmount } = wrap(<DocumentViewerPage id={ID} />);
    expect(await screen.findByTestId("registry-box")).toHaveTextContent("escrow evidence");
    unmount();
    const { ApiError } = await import("@/lib/api/client");
    vi.mocked(reg.getDocumentRegistry).mockRejectedValue(new ApiError(403, "x"));
    wrap(<DocumentViewerPage id={ID} />);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(reg.getDocumentRegistry).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("registry-box")).toBeNull();
  });

  it("supplier never requests it", async () => {
    vi.mocked(docs.getDocument).mockResolvedValue({ ...doc, viewer_role: "SUPPLIER" });
    wrap(<DocumentViewerPage id={ID} />);
    await screen.findByRole("heading", { level: 1 });
    expect(reg.getDocumentRegistry).not.toHaveBeenCalled();
    expect(screen.queryByTestId("registry-box")).toBeNull();
  });
});
