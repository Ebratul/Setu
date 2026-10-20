import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { receiptUrl } from "@/lib/audit/receipt";
import { parseExport } from "@/lib/audit/verify";
import type { AuditEntry, AuditEntryDetail, TamperOut } from "@/lib/api/audit";
import { VerifyPage } from "@/components/verify/VerifyPage";

import { ChainBlocks } from "./ChainBlocks";
import { EntryDrawer } from "./EntryDrawer";
import { TamperPanel } from "./TamperPanel";
import { suggestValue } from "./tamperModel";

const api = vi.hoisted(() => ({ tamperDemo: vi.fn(), getAuditEntry: vi.fn() }));
vi.mock("@/lib/api/audit", async (orig) => ({ ...(await orig<object>()), ...api }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

const FIX = path.resolve(import.meta.dirname, "../../../e2e/fixtures/audit");
const fixture = (f: string) => readFileSync(path.join(FIX, f), "utf-8");

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  vi.clearAllMocks();
});
const wrap = (ui: React.ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

const H = "a".repeat(64);
const entry = (seq: number, payload: Record<string, unknown> = {}): AuditEntry => ({
  seq,
  ts: "2026-10-19T10:00:00.000000Z",
  actor_type: "system",
  actor_id: "system",
  deal_id: null,
  action: seq === 4 ? "TRANCHE_RELEASED" : "DEAL_CREATED",
  tier: seq === 4 ? 2 : 0,
  decision: "OK",
  payload,
  payload_hash: H,
  prev_hash: H,
  entry_hash: `${seq}`.padEnd(64, "b"),
  signature: "c".repeat(128),
  key_id: "k",
  text_en: `Entry ${seq}`,
  text_bn: `এন্ট্রি ${seq}`,
});

describe("ChainBlocks", () => {
  it("colours blocks from the broken seq on, with text and icon", () => {
    wrap(<ChainBlocks judge brokenFrom={3} entries={[1, 2, 3, 4].map((s) => entry(s))} label="chain" />);
    const states = screen.getAllByTestId("chain-block").map((b) => b.getAttribute("data-state"));
    expect(states).toEqual(["ok", "ok", "broken", "broken"]);
    expect(within(screen.getAllByTestId("chain-block")[2]).getByText(/Broken/)).toBeInTheDocument();
  });

  it("draws a gap for a deleted entry and opens a block on click", () => {
    const onSelect = vi.fn();
    wrap(<ChainBlocks judge brokenFrom={3} missingSeq={3} entries={[entry(1), entry(2), entry(4)]} label="chain" onSelect={onSelect} />);
    expect(screen.getByTestId("chain-gap")).toHaveTextContent("seq 3 is missing");
    fireEvent.click(screen.getAllByTestId("chain-block")[0]);
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});

describe("TamperPanel", () => {
  it("pre-fills the amount example without arithmetic", () => {
    expect(suggestValue(entry(4, { amount: "5760.00" }), "amount")).toBe("57600.00");
  });

  it("runs an edit, shows the copy banner and the failing reason, then restores", async () => {
    const entries = [entry(1), entry(2), entry(3), entry(4, { amount: "5760.00" })];
    const out: TamperOut = {
      simulated: true,
      real_table_changed: false,
      report: {
        ok: false, entries_checked: 3, first_seq: 1, last_seq: 4, broken_seq: 4, reason: "hash_mismatch",
        detail: "payload_hash does not match", anchored: true,
    missing_seqs: 0, scheme: "setu-audit-v2", public_key_fingerprint: "f", verified_at: "2026-10-20T00:00:00Z",
      },
      entries: [...entries.slice(0, 3), entry(4, { amount: "57600.00" })],
    };
    api.tamperDemo.mockResolvedValue(out);
    wrap(<TamperPanel entries={entries} />);
    expect(screen.getByLabelText("New value")).toHaveValue("57600.00");
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the copy" }));
    await waitFor(() => expect(screen.getByTestId("tamper-verdict")).toHaveTextContent("Broken at seq 4: entry contents no longer match the hash"));
    expect(api.tamperDemo).toHaveBeenCalledWith({ mode: "edit", seq: 4, field: "amount", value: "57600.00" });
    expect(screen.getByText(/the real log was not changed/)).toBeInTheDocument();
    expect(screen.getAllByTestId("chain-block").map((b) => b.getAttribute("data-state"))).toEqual(["ok", "ok", "ok", "broken"]);
    fireEvent.click(screen.getByRole("button", { name: "Restore the live chain" }));
    expect(screen.queryByTestId("tamper-verdict")).toBeNull();
  });
});

describe("EntryDrawer", () => {
  it("shows the hashes and a verified badge, and closes on Escape", async () => {
    const detail: AuditEntryDetail = { ...entry(2), canonical: '{"seq":2}', verified: true, verify_reason: null };
    api.getAuditEntry.mockResolvedValue(detail);
    const onClose = vi.fn();
    wrap(<EntryDrawer seq={2} onClose={onClose} />);
    expect(screen.getByRole("dialog", { name: "Audit entry #2" })).toHaveAttribute("aria-modal", "true");
    await screen.findByText("Verified ✓");
    expect(screen.getByText('{"seq":2}')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("VerifyPage", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/verify");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(fixture("test-public-key.pem"))));
  });

  const upload = (testId: string, name: string, content: string) =>
    fireEvent.change(screen.getByTestId(testId), { target: { files: [new File([content], name)] } });

  it("labels both file inputs and says nothing is uploaded", async () => {
    wrap(<VerifyPage />);
    expect(screen.getByLabelText("Operation log (.jsonl)")).toBeInTheDocument();
    expect(screen.getByLabelText("Public key file (.pem)")).toBeInTheDocument();
    expect(screen.getByTestId("privacy-note")).toHaveTextContent("Nothing is uploaded");
    await screen.findByText(/Using the published/);
  });

  it("verifies the good log and flags a tampered one", async () => {
    wrap(<VerifyPage />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await screen.findByTestId("key-info");
    await waitFor(() => expect(screen.getByTestId("key-info")).toHaveTextContent("…"));
    upload("log-input", "good.jsonl", fixture("good.jsonl"));
    await waitFor(() => expect(screen.getByTestId("log-result")).toHaveTextContent("Verified ✓ 12 entries, seq 1..12"));
    upload("log-input", "bad.jsonl", fixture("tampered-amount.jsonl"));
    await waitFor(() => expect(screen.getByTestId("log-result")).toHaveTextContent("Broken at seq 10: entry contents no longer match the hash"));
    expect(screen.getByTestId("log-result")).toHaveAttribute("data-ok", "false");
  });

  it("verifies a receipt link and rejects a mismatching hash", async () => {
    const { entries } = parseExport(fixture("good.jsonl"));
    const url = new URL(receiptUrl(entries[9], "http://localhost"));
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    wrap(<VerifyPage />);
    await waitFor(() => expect(screen.getByTestId("receipt-result")).toHaveTextContent("Receipt valid"));
    cleanup();
    window.history.replaceState(null, "", `/verify?seq=10&hash=${"0".repeat(64)}${url.hash}`);
    wrap(<VerifyPage />);
    await waitFor(() => expect(screen.getByTestId("receipt-result")).toHaveTextContent("does not match the one on the receipt"));
  });
});
