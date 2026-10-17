import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, safeAppHref } from "./markdown";
import { splitAnswer } from "./messageParts";

describe("Markdown", () => {
  it("escapes raw HTML instead of rendering it", () => {
    const { container } = render(
      <Markdown text={'<script>alert(1)</script> **bold** <img src=x onerror=1>'} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
    expect(screen.getByText("bold").closest("strong")).not.toBeNull();
  });

  it("keeps internal /app links and drops external ones to plain text", () => {
    const { container } = render(
      <Markdown
        text={
          "[Cash flow](/app/cashflow) [evil](https://evil.example) [js](javascript:alert(1)) [odd](//evil.example/app)"
        }
      />,
    );
    const anchors = container.querySelectorAll("a");
    expect(anchors).toHaveLength(1);
    expect(anchors[0]).toHaveAttribute("href", "/app/cashflow");
    expect(screen.getByText("evil").tagName).toBe("SPAN");
  });

  it("renders bullets, italics and line breaks", () => {
    const { container } = render(
      <Markdown text={"_note_\nsecond line\n\n- one\n- two"} />,
    );
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("em")?.textContent).toBe("note");
    expect(container.querySelector("br")).not.toBeNull();
  });

  it("validates route shapes", () => {
    expect(safeAppHref("/app/orders/SETU-2026-0001/analysis")).not.toBeNull();
    expect(safeAppHref("/app/financing?date=2026-11-07&deal=SETU-2026-0001&amount=1560.00&currency=USD")).not.toBeNull();
    expect(safeAppHref("/app/../x")).toBeNull();
    expect(safeAppHref("https://x")).toBeNull();
    expect(safeAppHref(null)).toBeNull();
    expect(safeAppHref("/app%2F..")).toBeNull();
    expect(safeAppHref("/app/a/./b")).toBeNull();
    expect(safeAppHref("/apple")).toBeNull();
    expect(safeAppHref("/app\\evil")).toBeNull();
    expect(safeAppHref("\\app\\x")).toBeNull();
    expect(safeAppHref("/app/x\\y")).toBeNull();
  });

  it("keeps a javascript: query inert (still an internal path)", () => {
    const href = safeAppHref("/app?x=javascript:alert(1)");
    expect(href === null || href.startsWith("/app")).toBe(true);
    expect(href).toBeNull();
  });
});

describe("splitAnswer", () => {
  it("removes the Why line and notes from the body", () => {
    const parts = splitAnswer(
      "Answer here.\n\nWhy: because.\n\n_All figures are simulated demo data._",
      "Why: because.",
      ["_All figures are simulated demo data._"],
    );
    expect(parts.body).toBe("Answer here.");
    expect(parts.why).toBe("Why: because.");
    expect(parts.simulated).toBe(true);
  });
});
