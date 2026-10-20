export type SynthLike = {
  speak: (u: SpeechSynthesisUtterance) => void;
  cancel: () => void;
  getVoices: () => SpeechSynthesisVoice[];
};

export const READ_ALOUD_KEY = "setu_demo_readaloud";

export function pickVoice(voices: readonly { lang: string }[], lang: "en" | "bn") {
  const want = lang === "bn" ? "bn" : "en";
  const hit = voices.filter((v) => v.lang.toLowerCase().replace("_", "-").split("-")[0] === want);
  if (lang === "en") return hit.find((v) => v.lang.toLowerCase().replace("_", "-").startsWith("en-us")) ?? hit[0] ?? null;
  return hit[0] ?? null;
}

export type Speaker = {
  /** Speaks `text`; returns false when skipped (no support, or no Bangla voice). */
  speak: (text: string, lang: "en" | "bn") => boolean;
  cancel: () => void;
  supported: boolean;
};

type Utter = new (text: string) => { lang: string; voice: unknown; rate: number };

export function createSpeaker(synth: SynthLike | null | undefined, Utterance: Utter | undefined): Speaker {
  if (!synth || !Utterance) return { speak: () => false, cancel: () => {}, supported: false };
  return {
    supported: true,
    cancel: () => {
      try {
        synth.cancel();
      } catch {
        /* ignore */
      }
    },
    speak: (text, lang) => {
      if (!text.trim()) return false;
      try {
        const voice = pickVoice(synth.getVoices(), lang);
        if (lang === "bn" && !voice) return false;
        synth.cancel();
        const u = new Utterance(text);
        u.lang = voice ? (voice as { lang: string }).lang : lang === "bn" ? "bn-BD" : "en-US";
        u.voice = voice;
        u.rate = 1;
        synth.speak(u as unknown as SpeechSynthesisUtterance);
        return true;
      } catch {
        return false;
      }
    },
  };
}

export function browserSpeaker(): Speaker {
  if (typeof window === "undefined") return createSpeaker(null, undefined);
  return createSpeaker(window.speechSynthesis, window.SpeechSynthesisUtterance as unknown as Utter);
}

export function loadReadAloud(): boolean {
  try {
    return localStorage.getItem(READ_ALOUD_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveReadAloud(on: boolean) {
  try {
    localStorage.setItem(READ_ALOUD_KEY, on ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
}
