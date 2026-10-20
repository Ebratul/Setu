import { beforeEach, describe, expect, it, vi } from "vitest";

import { createSpeaker, loadReadAloud, pickVoice, saveReadAloud } from "./speech";

class FakeUtterance {
  lang = "";
  voice: unknown = null;
  rate = 0;
  constructor(public text: string) {}
}

function fakeSynth(voices: { lang: string; name: string }[]) {
  return {
    spoken: [] as FakeUtterance[],
    cancel: vi.fn(),
    getVoices: () => voices as unknown as SpeechSynthesisVoice[],
    speak(u: SpeechSynthesisUtterance) {
      this.spoken.push(u as unknown as FakeUtterance);
    },
  };
}

describe("speech wrapper", () => {
  it("picks voices by language prefix, preferring en-US", () => {
    const voices = [{ lang: "en-GB" }, { lang: "en_US" }, { lang: "bn-BD" }];
    expect(pickVoice(voices, "en")).toBe(voices[1]);
    expect(pickVoice(voices, "bn")).toBe(voices[2]);
    expect(pickVoice([{ lang: "en-GB" }], "bn")).toBeNull();
  });

  it("speaks English and cancels the previous utterance first", () => {
    const synth = fakeSynth([{ lang: "en-US", name: "x" }]);
    const sp = createSpeaker(synth, FakeUtterance);
    expect(sp.speak("Hello", "en")).toBe(true);
    expect(synth.cancel).toHaveBeenCalledTimes(1);
    expect(synth.spoken[0].text).toBe("Hello");
    expect(synth.spoken[0].lang).toBe("en-US");
  });

  it("silently skips Bangla when no Bangla voice exists", () => {
    const synth = fakeSynth([{ lang: "en-US", name: "x" }]);
    const sp = createSpeaker(synth, FakeUtterance);
    expect(sp.speak("নমস্কার", "bn")).toBe(false);
    expect(synth.spoken).toHaveLength(0);
  });

  it("speaks Bangla when a bn voice exists", () => {
    const synth = fakeSynth([{ lang: "bn-IN", name: "b" }]);
    expect(createSpeaker(synth, FakeUtterance).speak("নমস্কার", "bn")).toBe(true);
    expect(synth.spoken[0].lang).toBe("bn-IN");
  });

  it("does nothing without speechSynthesis and never throws", () => {
    const sp = createSpeaker(undefined, undefined);
    expect(sp.supported).toBe(false);
    expect(sp.speak("x", "en")).toBe(false);
    expect(() => sp.cancel()).not.toThrow();
    const broken = { cancel: () => { throw new Error("boom"); }, getVoices: () => [], speak: () => {} };
    expect(() => createSpeaker(broken, FakeUtterance).cancel()).not.toThrow();
    expect(createSpeaker(broken, FakeUtterance).speak("x", "en")).toBe(false);
  });

  it("skips empty text", () => {
    expect(createSpeaker(fakeSynth([]), FakeUtterance).speak("   ", "en")).toBe(false);
  });
});

describe("read-aloud preference", () => {
  beforeEach(() => localStorage.clear());
  it("persists in localStorage", () => {
    expect(loadReadAloud()).toBe(false);
    saveReadAloud(true);
    expect(loadReadAloud()).toBe(true);
  });
  it("survives unavailable storage", () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(loadReadAloud()).toBe(false);
    spy.mockRestore();
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => saveReadAloud(true)).not.toThrow();
    set.mockRestore();
  });
});
