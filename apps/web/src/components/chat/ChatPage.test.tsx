import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";

const replace = vi.fn();
let search = "";
const getThreadMessages = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));

vi.mock("@/lib/api/chat", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/chat")>("@/lib/api/chat");
  return {
    ...actual,
    listThreads: vi.fn().mockResolvedValue({ threads: [] }),
    getThreadMessages: (...a: unknown[]) => getThreadMessages(...a),
  };
});

vi.mock("@/lib/api/analysis", () => ({
  getOrders: vi.fn().mockResolvedValue({ orders: [] }),
}));

import { ChatPage } from "./ChatPage";

beforeEach(() => {
  getThreadMessages.mockReset().mockResolvedValue({ thread_id: "x", messages: [] });
  replace.mockReset();
});

describe("ChatPage ?thread= validation", () => {
  for (const bad of ["..", "../../x", "abc", "1/2"]) {
    it(`never loads messages for ${bad}`, async () => {
      search = `thread=${encodeURIComponent(bad)}`;
      render(
        <I18nProvider>
          <ChatPage />
        </I18nProvider>,
      );
      await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/chat", { scroll: false }));
      expect(getThreadMessages).not.toHaveBeenCalled();
    });
  }

  it("loads a valid UUID thread", async () => {
    search = "thread=2d42f939-9f61-4165-a7d1-2116ee68c0b9";
    render(
      <I18nProvider>
        <ChatPage />
      </I18nProvider>,
    );
    await waitFor(() => expect(getThreadMessages).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("Message to Setu")).toBeInTheDocument();
  });
});
