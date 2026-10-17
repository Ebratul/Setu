import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StreamEvent } from "@/lib/api/chat";

const events: { list: StreamEvent[] } = { list: [] };
const onThread = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/api/chat", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/chat")>("@/lib/api/chat");
  return {
    ...actual,
    streamChat: async function* () {
      for (const e of events.list) yield e;
    },
  };
});

import { MAX_ANSWER_CHARS, useChatSession } from "./useChatSession";
import type { AssistantMessage } from "./types";

describe("useChatSession limits", () => {
  it("shows the error state when the streamed answer is too long", async () => {
    events.list = [
      { type: "meta", thread_id: null, intent: null, model: null, language: "en" },
      { type: "token", text: "x".repeat(MAX_ANSWER_CHARS + 1) },
    ];
    const { result } = renderHook(() => useChatSession({ language: "en", onThread }));
    act(() => result.current.send("hi"));
    await waitFor(() => expect(result.current.busy).toBe(false));
    const a = result.current.messages[1] as AssistantMessage;
    expect(a.status).toBe("error");
    expect(onThread).not.toHaveBeenCalled();
    expect(result.current.threadId).toBeNull();
  });
});
