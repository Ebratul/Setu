export type SseEvent = { event: string; data: string };

export const MAX_SSE_BUFFER = 1_000_000;

export class SseLimitError extends Error {
  constructor() {
    super("SSE event too large");
    this.name = "SseLimitError";
  }
}

/**
 * Incremental Server-Sent Events parser. Feed decoded text chunks of any size;
 * complete events are returned as soon as their blank-line terminator arrives.
 * Handles LF, CRLF and bare CR line endings, multi-line `data:` and comments.
 */
export class SseParser {
  private buffer = "";
  private event = "";
  private data: string[] = [];
  private pendingCr = false;
  private pending = 0;

  push(chunk: string): SseEvent[] {
    let text = chunk;
    if (this.pendingCr) {
      this.pendingCr = false;
      if (text.startsWith("\n")) text = text.slice(1);
    }
    if (text.endsWith("\r")) this.pendingCr = true;
    this.buffer += text;
    const buf = this.buffer;
    const out: SseEvent[] = [];
    let start = 0;
    for (let i = 0; i < buf.length; i++) {
      const c = buf.charCodeAt(i);
      if (c !== 10 && c !== 13) continue;
      const ev = this.line(buf.slice(start, i));
      if (ev) out.push(ev);
      if (c === 13 && buf.charCodeAt(i + 1) === 10) i++;
      start = i + 1;
    }
    this.buffer = buf.slice(start);
    if (this.buffer.length > MAX_SSE_BUFFER || this.pending > MAX_SSE_BUFFER) {
      throw new SseLimitError();
    }
    return out;
  }

  /** Flush a final event that was not terminated by a blank line. */
  end(): SseEvent[] {
    const out: SseEvent[] = [];
    if (this.buffer) {
      const ev = this.line(this.buffer);
      this.buffer = "";
      if (ev) out.push(ev);
    }
    const last = this.dispatch();
    if (last) out.push(last);
    return out;
  }

  private dispatch(): SseEvent | null {
    if (this.data.length === 0) {
      this.event = "";
      this.pending = 0;
      return null;
    }
    const ev = { event: this.event || "message", data: this.data.join("\n") };
    this.event = "";
    this.data = [];
    this.pending = 0;
    return ev;
  }

  private line(line: string): SseEvent | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") {
      this.data.push(value);
      this.pending += value.length;
    }
    return null;
  }
}

/** Reads a fetch body as SSE events. Stops when the stream ends or the reader is cancelled. */
export async function* readSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const ev of parser.push(decoder.decode(value, { stream: true }))) {
        yield ev;
      }
    }
    for (const ev of parser.push(decoder.decode())) yield ev;
    for (const ev of parser.end()) yield ev;
  } finally {
    reader.releaseLock();
  }
}
