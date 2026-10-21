import { beforeEach, describe, expect, it } from "vitest";

import { readEmbed } from "./useEmbed";

function at(search: string) {
  window.history.replaceState({}, "", `/app/cashflow${search}`);
}

describe("readEmbed", () => {
  beforeEach(() => {
    sessionStorage.clear();
    at("");
  });

  it("is off by default", () => {
    expect(readEmbed()).toBe(false);
  });

  it("?embed=1 turns embed mode on", () => {
    at("?embed=1");
    expect(readEmbed()).toBe(true);
  });

  it("outside an iframe the flag is not remembered, so the parent tab never inherits it", () => {
    at("?embed=1");
    readEmbed();
    at("");
    expect(sessionStorage.getItem("setu_embed")).toBeNull();
    expect(readEmbed()).toBe(false);
  });

  it("inside an iframe it sticks for the rest of the session, and embed=0 clears it", () => {
    const top = Object.getOwnPropertyDescriptor(window, "top");
    Object.defineProperty(window, "top", { value: {}, configurable: true });
    try {
      at("?embed=1");
      expect(readEmbed()).toBe(true);
      at("");
      expect(readEmbed()).toBe(true);
      at("?embed=0");
      expect(readEmbed()).toBe(false);
      at("");
      expect(readEmbed()).toBe(false);
    } finally {
      if (top) Object.defineProperty(window, "top", top);
    }
  });
});
