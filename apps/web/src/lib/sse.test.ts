import { describe, expect, it } from "vitest";

import { MAX_SSE_BUFFER, readSse, SseLimitError, SseParser } from "./sse";

function collect(chunks: string[]) {
  const p = new SseParser();
  const out = chunks.flatMap((c) => p.push(c));
  return [...out, ...p.end()];
}

describe("SseParser", () => {
  it("parses events split mid-line and mid-event", () => {
    const evs = collect([
      "event: tok",
      "en\ndata: {\"text\"",
      ": \"hi\"}\n",
      "\nevent: final\ndata: {}\n\n",
    ]);
    expect(evs).toEqual([
      { event: "token", data: '{"text": "hi"}' },
      { event: "final", data: "{}" },
    ]);
  });

  it("joins multi-line data with newlines", () => {
    expect(collect(["event: x\ndata: a\ndata: b\n\n"])).toEqual([
      { event: "x", data: "a\nb" },
    ]);
  });

  it("handles CRLF, including a CR/LF split across chunks", () => {
    const evs = collect(["event: a\r\ndata: 1\r", "\n\r\n", "data: 2\r\n\r\n"]);
    expect(evs).toEqual([
      { event: "a", data: "1" },
      { event: "message", data: "2" },
    ]);
  });

  it("ignores comments and delivers error events", () => {
    const evs = collect([
      ": keep-alive\n\nevent: error\ndata: {\"code\":\"x\",\"message\":\"boom\"}\n\n",
    ]);
    expect(evs).toHaveLength(1);
    expect(evs[0].event).toBe("error");
    expect(JSON.parse(evs[0].data)).toEqual({ code: "x", message: "boom" });
  });

  it("flushes an unterminated trailing event on end", () => {
    expect(collect(["event: final\ndata: {}"])).toEqual([
      { event: "final", data: "{}" },
    ]);
  });
});

describe("SseParser limits and odd input", () => {
  it("throws on an oversized unterminated line", () => {
    const p = new SseParser();
    expect(() => p.push("data: " + "x".repeat(MAX_SSE_BUFFER + 1))).toThrow(
      SseLimitError,
    );
  });

  it("throws on an oversized multi-line event", () => {
    const p = new SseParser();
    const line = "data: " + "y".repeat(100_000) + "\n";
    expect(() => {
      for (let i = 0; i < 12; i++) p.push(line);
    }).toThrow(SseLimitError);
  });

  it("passes unknown event names through and treats a colon-less data field as empty", () => {
    expect(collect(["event: weird\ndata\n\n"])).toEqual([
      { event: "weird", data: "" },
    ]);
  });

  it("parses many lines in one chunk", () => {
    const chunk = Array.from({ length: 2000 }, (_, i) => `event: t\ndata: ${i}\n\n`).join("");
    const evs = collect([chunk]);
    expect(evs).toHaveLength(2000);
    expect(evs[1999].data).toBe("1999");
  });
});

describe("readSse", () => {
  it("decodes multi-byte characters split across chunks", async () => {
    const bytes = new TextEncoder().encode("event: token\ndata: আমি\n\n");
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, 20));
        c.enqueue(bytes.slice(20));
        c.close();
      },
    });
    const got = [];
    for await (const ev of readSse(body)) got.push(ev);
    expect(got).toEqual([{ event: "token", data: "আমি" }]);
  });
});
