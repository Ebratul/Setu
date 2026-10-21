import type { ChatCardData, Citation } from "@/lib/api/chat";
import type { SecurityCheck } from "@/lib/api/security";

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
      citations: Citation[];
      tools: ToolStep[];
      status: MessageStatus;
      error: string | null;
      messageId: string | null;
      feedback: "up" | "down" | null;
      stopped: string | null;
      retryText: string | null;
      security?: SecurityCheck | null;
    };

export type AssistantMessage = Extract<UiMessage, { role: "assistant" }>;
