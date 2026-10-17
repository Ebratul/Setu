import type { ChatCardData } from "@/lib/api/chat";

export type ToolStep = {
  id: string;
  name: string;
  status: "running" | "ok" | "error";
};

export type MessageStatus =
  | "streaming"
  | "done"
  | "error"
  | "aborted"
  | "interrupted";

export type UiMessage =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      why: string | null;
      notes: string[];
      cards: ChatCardData[];
      tools: ToolStep[];
      status: MessageStatus;
      error: string | null;
      messageId: string | null;
      feedback: "up" | "down" | null;
      stopped: string | null;
      retryText: string | null;
    };

export type AssistantMessage = Extract<UiMessage, { role: "assistant" }>;
