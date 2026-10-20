import { describe, expect, it } from "vitest";

import { isTypingTarget, SHORTCUTS } from "./shortcuts";

describe("shortcuts", () => {
  it("does not fire single-key shortcuts while typing", () => {
    expect(isTypingTarget(document.createElement("input"))).toBe(true);
    expect(isTypingTarget(document.createElement("textarea"))).toBe(true);
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isTypingTarget(editable)).toBe(true);
    expect(isTypingTarget(document.createElement("button"))).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
  it("documents the slash and palette shortcuts", () => {
    expect(SHORTCUTS.some((s) => s.keys.includes("/"))).toBe(true);
    expect(SHORTCUTS.some((s) => s.keys.includes("K"))).toBe(true);
  });
});
