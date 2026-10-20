import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { PrivacyXrayData } from "@/lib/privacy/types";

import { PrivacyXrayView } from "./PrivacyXray";
import { XrayButton } from "./XrayButton";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

const data = (over: Partial<PrivacyXrayData> = {}): PrivacyXrayData => ({
  kind: "message",
  available: true,
  stats: { masked_by_type: { ACCT: 1, PHONE: 1, NID: 1 }, protected: 3, leaked_count: 0, chars_sent: 80 },
  left: [
    {
      label: "Your message",
      segments: [
        { text: "Pay ", type: null, token: null },
        { text: "6222 0021", type: "ACCT", token: "⟦ACCT_1⟧" },
      ],
    },
  ],
  right: [
    {
      label: "Answer step",
      node: "answer",
      model: "claude-haiku-5-5",
      sent: true,
      segments: [
        { text: "Pay ", type: null, token: null },
        { text: "⟦ACCT_1⟧", type: "ACCT", token: "⟦ACCT_1⟧" },
      ],
    },
  ],
  ...over,
});

const wrap = (ui: React.ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});
afterEach(() => vi.unstubAllGlobals());

describe("PrivacyXrayView", () => {
  it("highlights typed segments on both sides with a type marker and screen-reader text", () => {
    wrap(<PrivacyXrayView data={data()} />);
    const marks = document.querySelectorAll('mark[data-type="ACCT"]');
    expect(marks).toHaveLength(2);
    expect(marks[1]).toHaveTextContent("⟦ACCT_1⟧");
    expect(marks[1]).toHaveTextContent("(account, ⟦ACCT_1⟧)");
    expect(screen.getByText("What you see")).toBeInTheDocument();
    expect(screen.getByText("What was sent to the AI")).toBeInTheDocument();
  });

  it("states the counts in plain words and shows a green Leaked: 0 badge", () => {
    wrap(<PrivacyXrayView data={data()} />);
    expect(screen.getByTestId("xray-summary")).toHaveTextContent(
      "3 identifiers protected: 1 NID, 1 phone number, 1 account",
    );
    expect(screen.getByTestId("leaked-badge")).toHaveTextContent("Leaked: 0");
    expect(screen.getByTestId("leaked-badge")).toHaveAttribute("data-leaked", "0");
    expect(screen.queryByTestId("not-sent-badge")).toBeNull();
  });

  it("flags leaks and not-sent calls", () => {
    const d = data();
    d.stats.leaked_count = 2;
    d.right[0].sent = false;
    wrap(<PrivacyXrayView data={d} />);
    expect(screen.getByTestId("leaked-badge")).toHaveTextContent("Leaked: 2");
    expect(screen.getByTestId("not-sent-badge")).toHaveTextContent("Not sent in this run");
  });

  it("explains when no record is available", () => {
    wrap(<PrivacyXrayView data={data({ available: false })} />);
    expect(screen.getByTestId("xray-unavailable")).toBeInTheDocument();
  });
});

describe("XrayButton", () => {
  it("lazily fetches on open and closes with Escape", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(data()), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    wrap(<XrayButton kind="message" id="m-1" />);
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Show what the AI saw" }));
    expect(screen.getByRole("dialog", { name: "What did the AI see?" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("xray")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0][0])).toContain("/privacy/messages/m-1");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
