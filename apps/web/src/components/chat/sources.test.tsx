import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { parseEvent, type ChatMessage, type Citation } from "@/lib/api/chat";

import kbBn from "./fixtures/kbBn.json";
import kbEn from "./fixtures/kbEn.json";
import { Markdown } from "./markdown";
import { MessageBubble } from "./MessageBubble";
import { rebuildMessages } from "./rebuild";
import { SourcesList } from "./SourcesList";
import type { AssistantMessage } from "./types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

const cite = (over: Partial<Citation> = {}): Citation => ({
  cite_id: "S1",
  source_id: "incoterms-basics",
  title: "Incoterms basics",
  heading_path: "Incoterms basics > FOB",
  source_type: "glossary",
  original_reference: "ICC Incoterms 2020",
  last_reviewed: "2026-10-17",
  disclaimer: "Verify with the official source.",
  ...over,
});

const wrap = (ui: React.ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

function msg(over: Partial<AssistantMessage> = {}): AssistantMessage {
  return {
    id: "a1",
    role: "assistant",
    text: "FOB means X. [S1] Also [S9].",
    why: null,
    notes: [],
    cards: [],
    citations: [cite()],
    tools: [],
    status: "done",
    error: null,
    messageId: "m1",
    feedback: null,
    stopped: null,
    retryText: null,
    ...over,
  };
}

describe("citation chips", () => {
  it("renders a chip for a known id and plain text for an unknown id", () => {
    const onCite = vi.fn();
    wrap(
      <Markdown
        text="A [S1] and B [S9]."
        cites={{ citations: new Map([["S1", cite()]]), onCite }}
      />,
    );
    const chip = screen.getByRole("button", { name: "Source S1: Incoterms basics" });
    fireEvent.click(chip);
    expect(onCite).toHaveBeenCalledWith("S1");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByText(/\[S9\]/)).toBeInTheDocument();
  });

  it("does not inject HTML through citation titles", () => {
    const evil = cite({ title: '<img src=x onerror=alert(1)><b>x</b>' });
    const { container } = wrap(
      <>
        <Markdown text="A [S1]" cites={{ citations: new Map([["S1", evil]]), onCite: vi.fn() }} />
        <SourcesList citations={[evil]} idPrefix="p" highlighted={null} />
      </>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<img src=x");
  });

  it("clicking a chip highlights and focuses the matching source entry", () => {
    wrap(<MessageBubble message={msg()} onRetry={vi.fn()} onRate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Source S1/ }));
    const entry = document.querySelector('[data-cite-entry="S1"]')!;
    expect(entry).toHaveAttribute("data-highlighted", "true");
    expect(entry).toHaveFocus();
  });
});

describe("SourcesList", () => {
  it("shows entry details, plain-text reference and the verify note (EN)", () => {
    const { container } = wrap(<SourcesList citations={[cite()]} idPrefix="p" highlighted={null} />);
    expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByText(/Incoterms basics$/)).toBeInTheDocument();
    expect(screen.getByText("Incoterms basics > FOB")).toBeInTheDocument();
    expect(screen.getByText("ICC Incoterms 2020")).toBeInTheDocument();
    expect(screen.getByText("Last reviewed Oct 17, 2026")).toBeInTheDocument();
    expect(screen.getByText("Verify with the official source.")).toBeInTheDocument();
    expect(screen.getByText("Simplified summaries — verify with the official source.")).toBeInTheDocument();
    expect(container.querySelector("a")).toBeNull();
  });

  it("renders in Bangla", () => {
    document.cookie = "setu_lang=bn; path=/";
    wrap(<SourcesList citations={[cite()]} idPrefix="p" highlighted={null} />);
    expect(screen.getByRole("heading", { name: "উৎস" })).toBeInTheDocument();
    expect(screen.getByText(/সর্বশেষ পর্যালোচনা/)).toBeInTheDocument();
    expect(screen.getByText("সহজ করা সারসংক্ষেপ — সরকারি উৎসে যাচাই করুন।")).toBeInTheDocument();
  });

  it("renders nothing without citations", () => {
    wrap(<SourcesList citations={[]} idPrefix="p" highlighted={null} />);
    expect(screen.queryByTestId("sources")).toBeNull();
  });
});

describe("MessageBubble with a citations card", () => {
  const card = (withheld: unknown[]) =>
    ({
      card_type: "citations",
      explanation_en: "e",
      explanation_bn: "b",
      simulated: true,
      explanation_codes: [],
      data: { query: "q", snippets: [], withheld, security_flags: [] },
    }) as unknown as AssistantMessage["cards"][number];

  it("does not render the card but shows the withheld notice when needed", () => {
    const { rerender } = wrap(
      <MessageBubble message={msg({ cards: [card([{ source_id: "x", heading_path: "h", codes: ["I"] }])] })} onRetry={vi.fn()} onRate={vi.fn()} />,
    );
    expect(screen.getByTestId("withheld")).toHaveTextContent(
      "Some passages were withheld because they contained instruction-like text.",
    );
    expect(document.querySelector("[data-card-type]")).toBeNull();
    expect(screen.queryByText("Simulated data")).toBeNull();
    rerender(
      <I18nProvider>
        <MessageBubble message={msg({ cards: [card([])] })} onRetry={vi.fn()} onRate={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.queryByTestId("withheld")).toBeNull();
  });
});

describe("history and stream parsing", () => {
  it("rebuild uses meta.citations", () => {
    const rows = [
      { id: "u", seq: 1, role: "user", content: "q", created_at: "", meta: null },
      { id: "a", seq: 2, role: "assistant", content: "x [S1]", created_at: "", meta: { citations: [cite(), { cite_id: "bad" }] } },
    ] as unknown as ChatMessage[];
    const a = rebuildMessages(rows)[1] as AssistantMessage;
    expect(a.citations).toHaveLength(1);
    expect(a.citations[0].title).toBe("Incoterms basics");
  });

  it("final events keep captured citations; fixtures carry [S1] markers", () => {
    for (const fx of [kbEn, kbBn]) {
      const ev = parseEvent("final", JSON.stringify(fx));
      expect(ev?.type === "final" && ev.response.citations).toHaveLength(1);
      expect(fx.answer).toContain("[S1]");
    }
  });

  it("renders the captured EN answer with a chip and a source entry", () => {
    const m = msg({ text: kbEn.answer, why: kbEn.why ?? null, notes: [], citations: kbEn.citations as Citation[] });
    wrap(<MessageBubble message={m} onRetry={vi.fn()} onRate={vi.fn()} />);
    const chip = screen.getByRole("button", { name: /Source S1/ });
    expect(chip).toHaveTextContent("[S1]");
    const src = screen.getByTestId("sources");
    expect(within(src).getAllByText(/Incoterms basics for Bangladesh importers/).length).toBeGreaterThan(0);
  });
});
