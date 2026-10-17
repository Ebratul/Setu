import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import type { ChatMessage } from "@/lib/api/chat";

import { Composer } from "./Composer";
import { dealFromRoute } from "./ChatDrawer";
import { MessageBubble } from "./MessageBubble";
import { rebuildMessages } from "./rebuild";
import { ThreadList } from "./ThreadList";
import { ToolChips } from "./ToolChips";
import type { AssistantMessage } from "./types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

beforeEach(() => {
  document.cookie = "setu_lang=en; path=/";
});

const wrap = (ui: React.ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

describe("Composer", () => {
  it("sends on Enter, keeps newline on Shift+Enter, and shows Stop while busy", () => {
    const onSend = vi.fn();
    const onStop = vi.fn();
    const { rerender } = wrap(<Composer busy={false} onSend={onSend} onStop={onStop} />);
    const box = screen.getByLabelText("Message to Setu");
    fireEvent.change(box, { target: { value: "hello" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(box).toHaveValue("");
    rerender(
      <I18nProvider>
        <Composer busy onSend={onSend} onStop={onStop} />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalled();
  });
});

function assistant(over: Partial<AssistantMessage> = {}): AssistantMessage {
  return {
    id: "a1",
    role: "assistant",
    text: "Body text.\n\nWhy: because.\n\n_All figures are simulated demo data._",
    why: "Why: because.",
    notes: ["_All figures are simulated demo data._"],
    cards: [],
    citations: [],
    tools: [],
    status: "done",
    error: null,
    messageId: "m1",
    feedback: null,
    stopped: null,
    retryText: "q",
    ...over,
  };
}

describe("MessageBubble", () => {
  it("separates the Why line and notes, shows Simulated, and rates", () => {
    const onRate = vi.fn();
    wrap(<MessageBubble message={assistant()} onRetry={vi.fn()} onRate={onRate} />);
    expect(screen.getByText("Body text.")).toBeInTheDocument();
    expect(screen.getByText("Why: because.")).toBeInTheDocument();
    expect(screen.getByText("Simulated data")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Helpful answer" }));
    expect(onRate).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), "up");
  });

  it("shows pressed feedback state, typing indicator and error retry", () => {
    const onRetry = vi.fn();
    const { rerender } = wrap(
      <MessageBubble message={assistant({ feedback: "down" })} onRetry={onRetry} onRate={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Not helpful" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    rerender(
      <I18nProvider>
        <MessageBubble message={assistant({ status: "streaming", text: "" })} onRetry={onRetry} onRate={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByTestId("typing")).toBeInTheDocument();
    rerender(
      <I18nProvider>
        <MessageBubble message={assistant({ status: "error", error: "boom" })} onRetry={onRetry} onRate={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledWith("a1");
  });
});

describe("ToolChips", () => {
  it("localises known tools and falls back for unknown ones", () => {
    wrap(
      <ToolChips
        tools={[
          { id: "1", name: "forecast_cashflow", status: "running" },
          { id: "2", name: "mystery_tool", status: "ok" },
        ]}
      />,
    );
    expect(screen.getByText("Checking your cash flow…")).toBeInTheDocument();
    expect(screen.getByText("Working on it…")).toBeInTheDocument();
  });
});

describe("rebuildMessages", () => {
  it("attaches tool cards to the following assistant answer and flags interrupted turns", () => {
    const card = { card_type: "alerts", data: {} } as unknown as ChatMessage["card"];
    const rows: ChatMessage[] = [
      { id: "u", seq: 1, role: "user", content: "hi", created_at: "", meta: null },
      { id: "t", seq: 2, role: "tool", content: "", created_at: "", meta: null, card },
      { id: "a", seq: 3, role: "assistant", content: "ans", created_at: "", meta: { why: "w", feedback: { rating: "up" } } },
      { id: "u2", seq: 4, role: "user", content: "again", created_at: "", meta: null },
      { id: "a2", seq: 5, role: "assistant", content: "", created_at: "", meta: { aborted: "client" } },
    ];
    const out = rebuildMessages(rows);
    const a = out[1] as AssistantMessage;
    expect(a.cards).toHaveLength(1);
    expect(a.feedback).toBe("up");
    const a2 = out[3] as AssistantMessage;
    expect(a2.status).toBe("interrupted");
    expect(a2.retryText).toBe("again");
  });
});

describe("ThreadList", () => {
  const threads = [
    { id: "t1", title: "Cash chat", language: "en" as const, deal_id: null, tokens_used: 0, created_at: "2026-10-01T00:00:00Z", updated_at: null },
  ];
  it("renames inline and confirms before deleting", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    wrap(
      <ThreadList threads={threads} activeId="t1" query="" onQuery={vi.fn()} onSelect={vi.fn()} onNew={vi.fn()} onRename={onRename} onDelete={onDelete} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Rename Cash chat" }));
    const input = screen.getByLabelText("Conversation title");
    fireEvent.change(input, { target: { value: "Renamed" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(onRename).toHaveBeenCalledWith("t1", "Renamed"));

    fireEvent.click(screen.getByRole("button", { name: "Delete Cash chat" }));
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith("t1"));
  });
});

describe("dealFromRoute", () => {
  it("scopes order pages and financing ?deal=", () => {
    expect(dealFromRoute("/app/orders/SETU-2026-0001/analysis", null)).toBe("SETU-2026-0001");
    expect(dealFromRoute("/app/financing", "SETU-2026-0002")).toBe("SETU-2026-0002");
    expect(dealFromRoute("/app/cashflow", "x")).toBeNull();
    expect(dealFromRoute("/app/orders", null)).toBeNull();
    expect(() => dealFromRoute("/app/orders/%E0%A4%A", null)).not.toThrow();
    expect(dealFromRoute("/app/orders/%E0%A4%A", null)).toBeNull();
    expect(dealFromRoute("/app/orders/a%20b", null)).toBeNull();
    expect(dealFromRoute("/app/financing", "x".repeat(65))).toBeNull();
  });
});
