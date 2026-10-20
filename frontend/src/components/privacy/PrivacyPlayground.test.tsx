import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { DryRunResult, Segment } from "@/lib/privacy/types";

import { PrivacyPlayground } from "./PrivacyPlayground";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const plain = (text: string): Segment => ({ text, type: null, token: null });
const typed = (text: string, type: string, token: string): Segment => ({ text, type, token });

function result(text: string): DryRunResult {
  const nid = text.indexOf("1990123456789");
  const obf = text.includes("০১৭১১");
  const hits: DryRunResult["hits"] = [];
  const source: Segment[] = [];
  if (nid >= 0) {
    hits.push({ type: "NID", start: nid, end: nid + 13, confidence: 0.97, token: "⟦NID_1⟧", obfuscated: false, label_en: "National ID", label_bn: "জাতীয় পরিচয়পত্র" });
    source.push(plain(text.slice(0, nid)), typed("1990123456789", "NID", "⟦NID_1⟧"), plain(text.slice(nid + 13)));
  } else {
    source.push(plain(text));
  }
  if (obf) {
    hits.push({ type: "PHONE", start: 0, end: 1, confidence: 0.9, token: "⟦PHONE_1⟧", obfuscated: true, label_en: "Phone number", label_bn: "ফোন নম্বর" });
  }
  return {
    simulated: true,
    mask_amounts: true,
    hits,
    source_segments: source,
    masked_segments: [plain("ID "), typed("⟦NID_1⟧", "NID", "⟦NID_1⟧")],
    masked: "ID ⟦NID_1⟧",
    ai_answer_masked: "Checked ⟦NID_1⟧",
    ai_answer_segments: [plain("Checked "), typed("⟦NID_1⟧", "NID", "⟦NID_1⟧")],
    restored_answer: "Checked 1990123456789",
    restored_segments: [plain("Checked "), typed("1990123456789", "NID", "⟦NID_1⟧")],
    stats: { masked_by_type: { NID: 1 }, protected: 1, leaked_count: 0, chars_sent: 10 },
  };
}

const fetchMock = vi.fn();

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
  fetchMock.mockReset();
  fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body)) as { text: string };
    return Promise.resolve(new Response(JSON.stringify(result(body.text)), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const mount = () =>
  render(
    <I18nProvider>
      <PrivacyPlayground />
    </I18nProvider>,
  );

describe("PrivacyPlayground", () => {
  it("is pre-filled, calls dry-run after the debounce and highlights the NID", async () => {
    mount();
    expect((screen.getByRole("textbox", { name: "Text to protect" }) as HTMLTextAreaElement).value).toContain("NID 1990123456789");
    expect(screen.getByTestId("dry-run-note")).toHaveTextContent("Simulated · nothing is stored");
    const live = await screen.findByTestId("live-source", undefined, { timeout: 2000 });
    await waitFor(() => expect(live.querySelector('mark[data-type="NID"]')).not.toBeNull());
    expect(fetchMock.mock.calls[0][0]).toContain("/privacy/dry-run");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toMatchObject({ mask_amounts: true });
    expect(screen.getByTestId("live-status")).toHaveTextContent("1 identifier found");
  });

  it("shows masked, answer and restored panes after Send to AI (dry run)", async () => {
    mount();
    await screen.findByTestId("live-source", undefined, { timeout: 2000 });
    fireEvent.click(screen.getByRole("button", { name: "Send to AI (dry run)" }));
    const masked = await screen.findByTestId("pane-masked");
    expect(masked).toHaveTextContent("⟦NID_1⟧");
    expect(screen.getByTestId("pane-answer")).toHaveTextContent(/Checked .*⟦NID_1⟧/);
    expect(screen.getByTestId("pane-restored")).toHaveTextContent(/Checked .*1990123456789/);
    expect(screen.getByTestId("leaked-badge")).toHaveTextContent("Leaked: 0");
  });

  it("inserts obfuscation examples and marks obfuscated detections", async () => {
    mount();
    expect(screen.queryByRole("button", { name: "Bangla digits" })).toBeNull();
    fireEvent.click(screen.getByLabelText("Show obfuscation handling"));
    fireEvent.click(screen.getByRole("button", { name: "Bangla digits" }));
    expect((screen.getByRole("textbox", { name: "Text to protect" }) as HTMLTextAreaElement).value).toContain("০১৭১১ ২২৩ ৩৪৪");
    fireEvent.click(screen.getByRole("button", { name: "Zero-width character" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Text to protect" }).value).toContain("‍");
    await waitFor(() => expect(screen.getByTestId("obfuscated-badge")).toHaveTextContent("Obfuscation handled"), {
      timeout: 2000,
    });
  });

  it("sends mask_amounts=false when the toggle is off", async () => {
    mount();
    await screen.findByTestId("live-source", undefined, { timeout: 2000 });
    fireEvent.click(screen.getByLabelText("Mask amounts"));
    await waitFor(
      () => {
        const last = fetchMock.mock.calls.at(-1);
        expect(JSON.parse(String(last?.[1].body))).toMatchObject({ mask_amounts: false });
      },
      { timeout: 2000 },
    );
  });
});
