import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { CreditRecord } from "@/lib/api/creditRecords";

vi.mock("@/lib/api/creditRecords", () => ({ getCreditRecord: vi.fn(), verifyCreditRecord: vi.fn() }));
import * as api from "@/lib/api/creditRecords";

import { CreditRecordCard } from "@/components/deals/CreditRecordCard";

const record = (over: Partial<CreditRecord> = {}): CreditRecord => ({
  simulated: true,
  id: "1",
  deal_ref: "SETU-2026-0001",
  issued_at: "2026-10-20T05:00:00Z",
  key_id: "8030dcc6c48c93f3",
  payload: {
    buyer: "Rahima Knitwear",
    supplier: "Shaoxing Huaxin",
    amount: "9600.00",
    currency: "USD",
    on_time: true,
    disputes: 0,
    evidence: [{}, {}, {}],
    completed_on: "2026-10-20",
  },
  payload_hash: "a".repeat(64),
  signature: "b".repeat(128),
  hash_ok: true,
  signature_ok: true,
  verified: true,
  public_key_pem: "x",
  ...over,
});
const renderIt = () => render(<I18nProvider><CreditRecordCard reference="SETU-2026-0001" /></I18nProvider>);

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
});

describe("CreditRecordCard", () => {
  it("shows key facts, hash, truncated signature and a verified badge", async () => {
    vi.mocked(api.getCreditRecord).mockResolvedValue(record());
    const { container } = renderIt();
    expect(await screen.findByText("Signature verified")).toBeInTheDocument();
    expect(container.querySelector('[data-demo="credit-record"]')).not.toBeNull();
    expect(screen.getByText("$9,600.00")).toBeInTheDocument();
    expect(screen.getByText("Rahima Knitwear")).toBeInTheDocument();
    expect(screen.getByTestId("crec-hash")).toHaveTextContent("a".repeat(64));
    expect(screen.getByTestId("crec-signature").textContent).toContain("…");
    expect(screen.getByTestId("crec-signature").textContent!.length).toBeLessThan(40);
    expect(screen.getByText("Simulated")).toBeInTheDocument();
  });

  it("verifies again with the displayed payload and signature", async () => {
    const rec = record();
    vi.mocked(api.getCreditRecord).mockResolvedValue(rec);
    vi.mocked(api.verifyCreditRecord).mockResolvedValue({ simulated: true, payload_hash: rec.payload_hash, verified: false });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Verify again" }));
    await waitFor(() => expect(api.verifyCreditRecord).toHaveBeenCalledWith(rec.payload, rec.signature));
    expect(await screen.findByText("Signature not verified")).toBeInTheDocument();
  });

  it("flags a record that does not verify", async () => {
    vi.mocked(api.getCreditRecord).mockResolvedValue(record({ verified: false, signature_ok: false }));
    renderIt();
    expect(await screen.findByText("Signature not verified")).toBeInTheDocument();
  });

  it("copies the full signature", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    vi.mocked(api.getCreditRecord).mockResolvedValue(record());
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("b".repeat(128)));
  });

  it("says so while no record exists yet", async () => {
    vi.mocked(api.getCreditRecord).mockResolvedValue(null);
    renderIt();
    expect(await screen.findByText(/being issued/)).toBeInTheDocument();
  });
});
