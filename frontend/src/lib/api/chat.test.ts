import { describe, expect, it, vi } from "vitest";

import financing from "@/components/chat/fixtures/financing.json";
import cashflow from "@/components/chat/fixtures/cashflow.json";

import { getThreadMessages, isUuid, parseEvent, validateCard } from "./chat";

const ID = "2d42f939-9f61-4165-a7d1-2116ee68c0b9";

describe("isUuid", () => {
  it("accepts UUIDs and rejects traversal or junk", () => {
    expect(isUuid(ID)).toBe(true);
    for (const bad of ["..", "../x", "", "abc", `${ID}/x`, null, 5]) {
      expect(isUuid(bad)).toBe(false);
    }
  });
});

describe("getThreadMessages", () => {
  it("rejects a non-UUID id without calling fetch", () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    expect(() => getThreadMessages("..")).toThrow();
    expect(f).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("parseEvent", () => {
  it("rejects null, array and non-JSON payloads", () => {
    expect(parseEvent("token", "null")).toBeNull();
    expect(parseEvent("token", "[1]")).toBeNull();
    expect(parseEvent("token", "not json")).toBeNull();
    expect(parseEvent("unknown", "{}")).toBeNull();
  });

  it("does not let the payload override the event type", () => {
    const ev = parseEvent("token", JSON.stringify({ type: "final", text: "hi" }));
    expect(ev).toEqual({ type: "token", text: "hi" });
  });

  it("handles meta without or with a bad thread_id", () => {
    expect(parseEvent("meta", "{}")).toMatchObject({ type: "meta", thread_id: null });
    expect(parseEvent("meta", JSON.stringify({ thread_id: "../x" }))).toMatchObject({
      thread_id: null,
    });
    expect(parseEvent("meta", JSON.stringify({ thread_id: ID }))).toMatchObject({
      thread_id: ID,
    });
  });

  it("drops malformed cards from tool_end and final instead of passing them on", () => {
    const bad = { card_type: "financing_comparison", explanation_en: "", explanation_bn: "", data: {} };
    const end = parseEvent("tool_end", JSON.stringify({ name: "x", id: "1", ok: true, card: bad }));
    expect(end).toMatchObject({ type: "tool_end", card: null });
    const good = parseEvent("tool_end", JSON.stringify({ name: "x", id: "1", ok: true, card: financing }));
    expect(good).toMatchObject({ card: { card_type: "financing_comparison" } });
    const fin = parseEvent(
      "final",
      JSON.stringify({ thread_id: ID, answer: "a", cards: [bad, cashflow, { card_type: "nope" }, 5] }),
    );
    expect(fin?.type === "final" && fin.response.cards).toHaveLength(1);
  });

  it("ignores a final event with a non-UUID thread or missing answer", () => {
    expect(parseEvent("final", JSON.stringify({ thread_id: "x", answer: "a" }))).toBeNull();
    expect(parseEvent("final", JSON.stringify({ thread_id: ID }))).toBeNull();
  });
});

describe("validateCard", () => {
  const base = { explanation_en: "e", explanation_bn: "b" };
  it("requires the arrays and objects each card type renders", () => {
    expect(validateCard({ ...base, card_type: "cashflow", data: { before: {}, upcoming: [] } })).toBeNull();
    expect(validateCard({ ...base, card_type: "alerts", data: { alerts: {} } })).toBeNull();
    expect(validateCard({ ...base, card_type: "scorecard", data: {} })).toBeNull();
    expect(validateCard({ ...base, card_type: "document_check", data: { deal_ref: "X", status: "FAILED", documents: {} } })).toBeNull();
    expect(validateCard({ ...base, card_type: "document_check", data: { deal_ref: "X", status: "FAILED", documents: [], focus: { reasons: {} } } })).toBeNull();
    expect(validateCard({ ...base, card_type: "document_check", data: { deal_ref: "X", status: "FAILED", documents: [], focus: null } })).not.toBeNull();
    expect(validateCard({ ...base, card_type: "fx_compare", data: {} })).toBeNull();
    expect(validateCard({ ...base, card_type: "monthly_summary", data: {} })).toBeNull();
    expect(validateCard({ ...base, card_type: "landed_cost", data: {} })).toBeNull();
    expect(validateCard({ ...base, card_type: "alerts", data: { alerts: [] } })).not.toBeNull();
    expect(validateCard(null)).toBeNull();
  });
});
