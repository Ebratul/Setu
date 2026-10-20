import { describe, expect, it } from "vitest";

import { isTypingTarget, presenterAction } from "./keys";

const el = (tag: string, extra: Record<string, unknown> = {}) => ({ tagName: tag, getAttribute: () => null, ...extra }) as unknown as EventTarget;

describe("presenter key handler guard", () => {
  it("maps the documented keys", () => {
    const map: [string, string][] = [
      ["ArrowRight", "next"],
      ["ArrowLeft", "prev"],
      [" ", "toggle"],
      ["r", "reset"],
      ["R", "reset"],
      ["b", "blackout"],
      ["n", "notes"],
      ["f", "fullscreen"],
    ];
    for (const [key, action] of map) expect(presenterAction({ key, target: el("BODY") })).toBe(action);
    expect(presenterAction({ key: "x", target: el("BODY") })).toBeNull();
  });

  it("ignores keys while typing in a field", () => {
    for (const tag of ["INPUT", "TEXTAREA", "SELECT"]) {
      expect(presenterAction({ key: "ArrowRight", target: el(tag) })).toBeNull();
      expect(presenterAction({ key: "r", target: el(tag) })).toBeNull();
    }
    expect(presenterAction({ key: "n", target: el("DIV", { isContentEditable: true }) })).toBeNull();
    expect(isTypingTarget({ tagName: "DIV", getAttribute: () => "textbox" } as unknown as EventTarget)).toBe(true);
  });

  it("ignores modified keys so browser shortcuts keep working", () => {
    expect(presenterAction({ key: "r", ctrlKey: true, target: el("BODY") })).toBeNull();
    expect(presenterAction({ key: "ArrowLeft", altKey: true, target: el("BODY") })).toBeNull();
    expect(presenterAction({ key: "f", metaKey: true, target: el("BODY") })).toBeNull();
  });

  it("leaves Space to focused buttons and links", () => {
    expect(presenterAction({ key: " ", target: el("BUTTON") })).toBeNull();
    expect(presenterAction({ key: " ", target: el("A") })).toBeNull();
    expect(presenterAction({ key: " ", target: el("SUMMARY") })).toBeNull();
  });
});
